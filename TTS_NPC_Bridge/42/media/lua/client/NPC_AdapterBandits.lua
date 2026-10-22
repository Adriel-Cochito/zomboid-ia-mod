-- =====================================================================
-- NPC_AdapterBandits.lua  (adapter do Bandits 2 / B42.21 para a ponte TTS)
-- Cria e acompanha 1 companheiro amigavel. A ponte NAO muda.
-- Fatos baseados no codigo do Bandits (BanditServerSpawner.lua, ZPCompanion.lua):
--   * criar: sendClientCommand(player, 'Spawner', 'Clan', args)
--   * dono do NPC: brain.master == BanditUtils.GetCharacterID(player)
--   * programa "Companion" = segue o mestre e ataca inimigos a menos de 8 tiles
--   * trocar de modo: BanditMenu.SwitchProgram(player, npc, programa)  (o mesmo que o
--     menu "Join Me!/Leave Me!" do proprio Bandits usa)
-- Observacoes: o Kahlua do PZ nao tem next(); "saquear" nao existe para companheiros
-- no Bandits (o loot do Companion esta desativado no codigo deles).
-- Mantenha NPC_AdapterStub.lua com ENABLE_STUB = false.
-- =====================================================================
require "NPC_Bridge"

local TAG = "[NPC BANDITS] "
local Adapter = { name = "Bandits" }

-- ---- Configuracao ----------------------------------------------------
local PREFERRED_CLAN_NAME = ""        -- nome exato do seu cla no Creator ("" = automatico)
local SILENCE_BANDITS_SPEECH = true   -- desliga General_Speak/Captions (so a nossa voz fala)
local SPAWN_OFFSET = 2                -- tiles ao lado do jogador
local RESCAN_MS = 1500                -- intervalo minimo entre buscas do companheiro
local REQUIRE_VEHICLE = true          -- "entrar no carro" so funciona perto de um veiculo
local BOARD_MAX_DIST = 15             -- distancia maxima (tiles) do companheiro para embarcar
local PENDING_TIMEOUT_MS = 6000       -- espera pelo NPC recriado antes do proximo metodo
local NOVEHICLE_TIMEOUT_MS = 120000  -- se nao entrar em veiculo em 2 min, ele volta sozinho
local MAX_ROLLS = 12                  -- tentativas de sortear o mesmo membro do cla (fallback)
local FETCH_RADIUS = 25               -- raio (tiles) da busca de itens
local FETCH_MAX_MS = 90000            -- tempo maximo de uma busca
local FETCH_MAX_TAKE = 8              -- maximo de itens por busca

-- Modos canonicos -> programas do Bandits
--   Companion = segue o mestre e ataca inimigos a menos de 8 tiles
--   Looter    = e o "Leave Me!" do Bandits: fica parado e so reage a inimigos
--   (CompanionGuard volta sozinho para Companion se nao houver posto de guarda)
local MODE_TO_PROGRAM = {
    seguir   = "Companion",
    defender = "Companion",
    ficar    = "CompanionStay",
    -- saquear: nao suportado pelo Bandits para companheiros (vira busca, ver Adapter.fetch)
}
local PROGRAM_TO_MODE = {
    Looter = "ficar", CompanionStay = "ficar", CompanionGuard = "ficar",
    Defend = "defender", CompanionFetch = "seguir",
}
local STAY_LEASH = 8    -- tiles: se for empurrado para longe do posto, ele volta
local STAY_NOTICE = 20  -- tiles: so vira o rosto pra ameaca proxima (nao sai perseguindo)

-- ---- Utilidades --------------------------------------------------------
local function now()
    if getTimestampMs then return getTimestampMs() end
    return 0
end

local function bandits_ready()
    return type(BanditBrain) == "table" and type(BanditBrain.Get) == "function"
        and type(BanditUtils) == "table" and type(BanditUtils.GetCharacterID) == "function"
end

local function myId(player)
    local ok, id = pcall(BanditUtils.GetCharacterID, player)
    if ok then return id end
    return nil
end

local function brainOf(z)
    local ok, b = pcall(BanditBrain.Get, z)
    if ok and type(b) == "table" then return b end
    return nil
end

local function hasAny(t)
    for _ in pairs(t) do return true end
    return false
end

local function isMine(z, pid)
    local b = brainOf(z)
    if not b or b.hostile then return false end
    return b.master == pid
end

-- ---- Localizar o companheiro (com cache) --------------------------------
local cache = { z = nil, t = -100000 }
local currentMode = "seguir"

-- Embarque "de mentira": o NPC some e volta quando o jogador desce do veiculo.
-- board   = foto do NPC guardada (persiste no save, em player:getModData().ttsBoard)
-- pending = NPC sendo recriado apos desembarcar
local board, pending, boardLoaded = nil, nil, false
local boardedAt, wasSeenInVehicle = 0, false
local fetchJob, fetchResult = nil, nil   -- busca de itens em andamento / resultado a reportar

local function loadBoard(player)
    if boardLoaded or not player then return end
    boardLoaded = true
    local ok, md = pcall(function() return player:getModData() end)
    if ok and md and type(md.ttsBoard) == "table" then
        if md.ttsBoard.bid and not md.ttsBoard.inPlace then
            board = md.ttsBoard
            boardedAt = getTimestampMs and getTimestampMs() or 0
        else
            md.ttsBoard = nil -- formato de versao anterior: descarta
        end
    end
end

local function saveBoard(player)
    pcall(function() player:getModData().ttsBoard = board end)
end

local function findCompanion(player)
    if not player or not bandits_ready() then return nil end
    local pid = myId(player)
    if pid == nil then return nil end

    local z = cache.z
    if z then
        local ok, dead = pcall(function() return z:isDead() end)
        if ok and not dead and isMine(z, pid) then return z end
        cache.z = nil
    end

    local t = now()
    if t - cache.t < RESCAN_MS then return nil end
    cache.t = t

    local cell = player:getCell()
    local list = cell and cell:getZombieList()
    if not list then return nil end
    for i = 0, list:size() - 1 do
        local cand = list:get(i)
        if cand and isMine(cand, pid) then
            cache.z = cand
            return cand
        end
    end
    return nil
end

-- ---- Cla amigavel para o spawn ---------------------------------------------
local function chooseClan()
    if type(BanditCustom) ~= "table" then return nil end
    local ok, all = pcall(BanditCustom.ClanGetAll)
    if not ok or type(all) ~= "table" then return nil end
    local cands = {}
    for cid, clan in pairs(all) do
        local spawn = clan.spawn or {}
        local name = (clan.general and clan.general.name) or ""
        local okm, members = pcall(BanditCustom.GetFromClan, cid)
        if okm and type(members) == "table" and hasAny(members) then
            if PREFERRED_CLAN_NAME ~= "" and name == PREFERRED_CLAN_NAME then return cid, name end
            if spawn.friendly then
                cands[#cands + 1] = { cid = cid, name = name, rank = spawn.companion and 0 or 1 }
            end
        end
    end
    table.sort(cands, function(a, b)
        if a.rank ~= b.rank then return a.rank < b.rank end
        return tostring(a.name) < tostring(b.name)
    end)
    if cands[1] then return cands[1].cid, cands[1].name end
    return nil
end

local function silenceBandits()
    if not SILENCE_BANDITS_SPEECH then return end
    pcall(function()
        if SandboxVars and type(SandboxVars.Bandits) == "table" then
            SandboxVars.Bandits.General_Speak = false
            SandboxVars.Bandits.General_Captions = false
        end
    end)
end

local function spawnCompanion(playerNum)
    local player = getSpecificPlayer(playerNum)
    if not player then return end
    cache.t = -100000
    if findCompanion(player) then
        player:Say("Ja tenho um companheiro.")
        return
    end
    local cid, name = chooseClan()
    if not cid then
        player:Say("Sem cla amigavel com membros (crie um no Bandits Creator).")
        print(TAG .. "nenhum cla amigavel com membros encontrado")
        return
    end
    silenceBandits()
    local args = {
        cid = cid, size = 1, program = "Companion",
        hostile = false, hostileP = false,
        x = math.floor(player:getX()) + SPAWN_OFFSET,
        y = math.floor(player:getY()),
        z = player:getZ(),
    }
    print(TAG .. "spawn do cla '" .. tostring(name) .. "' (" .. tostring(cid) .. ")")
    sendClientCommand(player, "Spawner", "Clan", args)
    cache.t = -100000
end

-- ---- Contrato da ponte ---------------------------------------------------------
function Adapter.hasNpc(player)
    loadBoard(player)
    return board ~= nil or pending ~= nil or findCompanion(player) ~= nil
end

function Adapter.isNpcNearby(player, worldobjects)
    loadBoard(player)
    return board ~= nil or pending ~= nil or findCompanion(player) ~= nil
end

function Adapter.npcName(player)
    loadBoard(player)
    if board then return tostring(board.fullname or "Companheiro") end
    local z = findCompanion(player)
    local b = z and brainOf(z)
    if b and b.fullname and b.fullname ~= "" then return tostring(b.fullname) end
    return "Companheiro"
end

local function countThreats(z)
    local cell = z:getCell()
    local list = cell and cell:getZombieList()
    if not list then return 0 end
    local zx, zy = z:getX(), z:getY()
    local n = 0
    for i = 0, list:size() - 1 do
        local o = list:get(i)
        if o and o ~= z then
            local dx, dy = o:getX() - zx, o:getY() - zy
            if dx * dx + dy * dy <= 25 and not brainOf(o) then
                local ok, dead = pcall(function() return o:isDead() end)
                if ok and not dead then n = n + 1 end
            end
        end
    end
    return n
end

local function readHp(z)
    local ok, h = pcall(function() return z:getHealth() end)
    if not ok or type(h) ~= "number" then return 100 end
    return math.max(0, math.min(100, math.floor(h * 100)))
end

local function readAmmo(z)
    if type(Bandit) ~= "table" then return "ok" end
    local ok, bare = pcall(Bandit.IsBareHands, z)
    if ok and bare then return "none" end
    local ok2, empty = pcall(Bandit.IsOutOfAmmo, z)
    if ok2 and empty then return "empty" end
    return "ok"
end

local function readMode(z)
    local b = brainOf(z)
    local prog = b and b.program and b.program.name
    if prog and PROGRAM_TO_MODE[prog] then return PROGRAM_TO_MODE[prog] end
    if currentMode == "defender" then return "defender" end
    return "seguir"
end

function Adapter.getState(player)
    loadBoard(player)
    local z = findCompanion(player)
    local bd = player:getBodyDamage()
    if not z then
        if not (board or pending) then return nil end
        local snap = board or pending.snap
        return {
            name = tostring(snap.fullname or "Companheiro"),
            mode = snap.mode or "seguir",
            hp = snap.hp100 or 100,
            player_hp = bd and math.floor(bd:getOverallBodyHealth()) or 100,
            threats = 0, ammo = "ok", loot_near = 0,
        }
    end
    return {
        name = Adapter.npcName(player),
        mode = readMode(z),
        hp = readHp(z),
        player_hp = bd and math.floor(bd:getOverallBodyHealth()) or 100,
        threats = countThreats(z),
        ammo = readAmmo(z),
        loot_near = 0,
    }
end

function Adapter.setMode(player, mode)
    loadBoard(player)
    if fetchJob then
        print(TAG .. "modo '" .. tostring(mode) .. "' ignorado: busca em andamento")
        return
    end
    local z = findCompanion(player)
    local program = MODE_TO_PROGRAM[mode]
    if not z then
        if board and program then board.mode = mode; saveBoard(player) end
        return
    end
    if mode == "ficar" then
        local b = brainOf(z)
        if b then b.ttsPost = { x = z:getX(), y = z:getY(), z = z:getZ() } end
    end
    if mode == "ficar" then
        local b = brainOf(z)
        if b then b.ttsPost = { x = z:getX(), y = z:getY(), z = z:getZ() } end
    end
    if not program then
        print(TAG .. "modo '" .. tostring(mode) .. "' nao suportado pelo Bandits (ignorado)")
        return
    end
    local ok, err
    if type(BanditMenu) == "table" and type(BanditMenu.SwitchProgram) == "function" then
        ok, err = pcall(BanditMenu.SwitchProgram, player, z, program)
    elseif type(Bandit) == "table" and type(Bandit.SetProgram) == "function" then
        ok, err = pcall(Bandit.SetProgram, z, program, {})
    else
        print(TAG .. "nenhuma funcao de troca de programa disponivel")
        return
    end
    if ok then
        currentMode = mode
        print(TAG .. "modo " .. mode .. " -> programa " .. program)
    else
        print(TAG .. "SetProgram falhou: " .. tostring(err))
    end
end

function Adapter.say(player, text)
    local z = findCompanion(player)
    if z then pcall(function() z:Say(text) end) end
end

-- ---- Embarcar / desembarcar (fingir que entrou no carro) -----------------------------
local function nearVehicle(player)
    local ok, v = pcall(function() return player:getVehicle() or player:getNearVehicle() end)
    if not ok then return true end -- API ausente: nao bloqueia
    return v ~= nil
end

local function collectItems(z)
    local out = {}
    pcall(function()
        local items = z:getInventory():getItems()
        for i = 0, items:size() - 1 do
            local it = items:get(i)
            if it then out[#out + 1] = it:getFullType() end
        end
    end)
    return out
end

local function freeSpotNear(player)
    local px, py, pz = math.floor(player:getX()), math.floor(player:getY()), player:getZ()
    local offs = { {2,0},{-2,0},{0,2},{0,-2},{3,0},{-3,0},{0,3},{0,-3},{2,2},{-2,-2},{2,-2},{-2,2} }
    local cell = player:getCell()
    for _, o in ipairs(offs) do
        local ok, sq = pcall(function() return cell:getGridSquare(px + o[1], py + o[2], pz) end)
        if ok and sq then
            local okf, free = pcall(function() return sq:isFree(false) and not sq:getVehicleContainer() end)
            if okf and free then return px + o[1], py + o[2], pz end
        end
    end
    return px + SPAWN_OFFSET, py, pz
end

-- Liga/desliga o "fantasma" por tempo curto (so entre o renascer e o teleporte/revelar).
-- Cada chamada e tentada separadamente pois as APIs variam entre builds do PZ.
local hideLogged = false
local function setHidden(z, hidden)
    local res = {}
    local function try(name, f)
        local ok = pcall(f)
        res[#res + 1] = name .. (ok and "+" or "-")
    end
    local a = hidden and 0 or 1
    try("invisible", function() z:setInvisible(hidden) end)
    try("god",       function() z:setGodMod(hidden) end)
    try("alpha0",    function() z:setAlphaAndTarget(a, 0.1) end)
    if not hideLogged or not hidden then
        hideLogged = hidden
        print(TAG .. (hidden and "ocultar: " or "mostrar: ") .. table.concat(res, " "))
    end
end

local function moveTo(z, x, y, zz)
    pcall(function() z:setX(x) end)
    pcall(function() z:setY(y) end)
    pcall(function() z:setZ(zz) end)
end

local function boardCompanion(playerNum)
    local player = getSpecificPlayer(playerNum)
    if not player then return end
    loadBoard(player)
    if board or pending then player:Say("Ele ja esta no carro."); return end
    local z = findCompanion(player)
    if not z then player:Say("Nenhum companheiro por perto."); return end
    local dx, dy = z:getX() - player:getX(), z:getY() - player:getY()
    if dx * dx + dy * dy > BOARD_MAX_DIST * BOARD_MAX_DIST then
        player:Say("Ele esta longe demais."); return
    end
    if REQUIRE_VEHICLE and not nearVehicle(player) then
        player:Say("Chegue perto do carro."); return
    end
    local b = brainOf(z)
    if not b or not b.bid then
        print(TAG .. "brain sem 'bid': nao da para recriar o NPC depois (embarque cancelado)")
        player:Say("Nao consigo guardar ele.")
        return
    end
    local hp = 1
    pcall(function() hp = z:getHealth() end)
    board = {
        bid = b.bid, cid = b.cid, fullname = b.fullname, voice = b.voice,
        hp = hp, hp100 = readHp(z), mode = currentMode, items = collectItems(z),
    }
    saveBoard(player)
    print(TAG .. "embarcou: " .. tostring(board.fullname) .. " (" .. #board.items .. " itens guardados)")
    boardedAt, wasSeenInVehicle = now(), false
    fetchJob = nil
    pcall(BanditBrain.Remove, z)
    pcall(function() z:removeFromWorld() end)
    pcall(function() z:removeFromSquare() end)
    cache.z, cache.t = nil, -100000
end

local function removeZombie(z)
    pcall(BanditBrain.Remove, z)
    pcall(function() z:removeFromWorld() end)
    pcall(function() z:removeFromSquare() end)
end

-- how = "individual": mesmo membro (bid). how = "clan": caminho comprovado (Spawner.Clan),
-- que sorteia um membro do cla; o nome e a voz sao forcados e o sorteio e repetido ate vir o mesmo bid.
-- a localizacao devolvida (x,y,z do carro, sem colisao) e onde ele "renasce" escondido;
-- so depois de REVEAL_DELAY_MS e que ele anda (teleporta) pra um lugar livre e aparece.
local REVEAL_DELAY_MS = 900
local revealJob = nil  -- { mode=.., t=.. }

local function spawnFromSnap(player, snap, how, x, y, z)
    if not (x and y and z) then x, y, z = freeSpotNear(player) end
    if how == "clan" then
        sendClientCommand(player, "Spawner", "Clan", {
            cid = snap.cid, size = 1, program = "Companion",
            hostile = false, hostileP = false,
            fullname = snap.fullname, voice = snap.voice,
            x = x, y = y, z = z,
        })
    else
        sendClientCommand(player, "Spawner", "Individual", {
            bid = snap.bid, program = "Companion",
            hostile = false, hostileP = false,
            fullname = snap.fullname, voice = snap.voice,
            x = x, y = y, z = z,
        })
    end
end

local function unboardCompanion(player)
    loadBoard(player)
    if not board or pending then return end
    cache.t = -100000
    local px, py, pz = player:getX(), player:getY(), player:getZ()
    if findCompanion(player) then
        -- a remocao nao pegou: ele ainda esta no mundo, entao nao duplica
        print(TAG .. "desembarque: NPC ainda existe, nada a recriar")
        board = nil; saveBoard(player)
        return
    end
    silenceBandits()
    pending = { snap = board, t = now(), how = "individual", rolls = 0, px = px, py = py, pz = pz }
    print(TAG .. "desembarcando " .. tostring(board.fullname))
    spawnFromSnap(player, board, "individual", px, py, pz)
end

local function applyPending(player)
    if not pending then return end
    cache.t = -100000
    local z = findCompanion(player)
    local snap = pending.snap
    if z then
        local b = brainOf(z)
        if pending.how == "clan" and snap.bid and b and b.bid ~= snap.bid and pending.rolls < MAX_ROLLS then
            -- veio outro membro do cla: descarta e sorteia de novo
            pending.rolls = pending.rolls + 1
            removeZombie(z)
            cache.z, cache.t = nil, -100000
            pending.t = now()
            spawnFromSnap(player, snap, "clan", pending.px, pending.py, pending.pz)
            return
        end
        pcall(function()
            if snap.hp and snap.hp < z:getHealth() then z:setHealth(snap.hp) end
        end)
        pcall(function()
            local inv = z:getInventory()
            for _, ft in ipairs(snap.items or {}) do inv:AddItem(ft) end
        end)
        -- ele "renasceu" dentro/perto do carro: fica escondido e parado por um instante,
        -- so entao teleporta pra um lugar livre e aparece (sem correr ate la)
        setHidden(z, true)
        if type(BanditMenu) == "table" and type(BanditMenu.SwitchProgram) == "function" then
            pcall(BanditMenu.SwitchProgram, player, z, "Looter")
        end
        revealJob = { mode = snap.mode or "seguir", t = now() + REVEAL_DELAY_MS }
        local mode = snap.mode
        board, pending = nil, nil
        saveBoard(player)
        print(TAG .. "companheiro de volta (escondido " .. REVEAL_DELAY_MS .. "ms): " .. tostring(snap.fullname))
        return
    end
    local t = now()
    if t - pending.t > PENDING_TIMEOUT_MS then
        if pending.how == "individual" then
            print(TAG .. "Spawner.Individual nao gerou o NPC; tentando via cla")
            pending.how, pending.rolls, pending.t = "clan", 0, t
            spawnFromSnap(player, snap, "clan", pending.px, pending.py, pending.pz)
        else
            print(TAG .. "falha ao recriar o NPC; use o menu 'desembarcar' para tentar de novo")
            pending = nil
        end
    end
end

-- ver a mochila do companheiro (itens do inventario real do NPC, ou os guardados no carro)
local function showBackpack(playerNum)
    local player = getSpecificPlayer(playerNum)
    if not player then return end
    loadBoard(player)
    local counts, order = {}, {}
    local function add(n)
        if not counts[n] then counts[n] = 0; order[#order + 1] = n end
        counts[n] = counts[n] + 1
    end
    if board then
        for _, ft in ipairs(board.items or {}) do add(ft) end
    else
        local z = findCompanion(player)
        if z then
            pcall(function()
                local items = z:getInventory():getItems()
                for i = 0, items:size() - 1 do
                    local it = items:get(i)
                    if it then add(it:getDisplayName()) end
                end
            end)
        end
    end
    local lines = {}
    for _, n in ipairs(order) do lines[#lines + 1] = counts[n] .. "x " .. n end
    local text = #lines > 0 and table.concat(lines, " <LINE> ") or "(mochila vazia)"
    print(TAG .. "mochila: " .. (#lines > 0 and table.concat(lines, ", ") or "vazia"))
    local ok = pcall(function()
        local w, h = 320, 260
        local core = getCore()
        local modal = ISModalRichText:new((core:getScreenWidth() - w) / 2, (core:getScreenHeight() - h) / 2,
            w, h, "Mochila de " .. Adapter.npcName(player) .. " <LINE> <LINE> " .. text, false, nil, nil, playerNum)
        modal:initialise()
        modal:addToUIManager()
    end)
    if not ok then player:Say("Mochila: " .. (#lines > 0 and table.concat(lines, ", ") or "vazia")) end
end

-- ---- Buscar itens (programa proprio "CompanionFetch") ---------------------------------
-- O Bandits nao tem loot para companheiro, entao criamos um programa simples:
-- escaneia contêineres num raio, anda ate o mais proximo que tenha o item, transfere para o
-- inventario do NPC e volta ao programa Companion. Palavras-chave (vindas do daemon):
--   "petrol"   = nome/tipo contem o texto      "-empty" = exclui     "cat:Food" = categoria
--   "@util"    = comida, remedios, combustivel, municao
local function kwList(csv)
    local pos, neg, cats = {}, {}, {}
    for raw in string.gmatch(tostring(csv or ""), "[^,]+") do
        local w = string.lower((string.gsub(raw, "^%s*(.-)%s*$", "%1")))
        if string.sub(w, 1, 1) == "-" then neg[#neg + 1] = string.sub(w, 2)
        elseif string.sub(w, 1, 4) == "cat:" then cats[#cats + 1] = string.sub(w, 5)
        elseif w ~= "" then pos[#pos + 1] = w end
    end
    return { pos = pos, neg = neg, cats = cats, util = (string.find(tostring(csv or ""), "@util", 1, true) ~= nil) }
end

-- "@util" deixou de incluir comida comum (tudo o que vira junk/bicho/perecivel
-- acabava entrando). Agora e so o que e sempre relevante: remedio, municao, combustivel.
local UTIL_CATS = { firstaid = true }
local UTIL_WORDS = { "petrol", "ammo", "bullet" }

-- nunca pega (bicho, lixo, nojeira) nenhuma categoria/palavra-chave traz isso de volta
local JUNK_WORDS = {
    "barata", "mosca", "aranha", "inseto", "minhoca", "rato", "lesma", "lagarta", "verme",
    "cockroach", "fly", "spider", "maggot", "worm", "rotten", "estragad", "podre",
}
local JUNK_CATS = { garbage = true, junk = true, trash = true }

local function itemMatches(item, kw)
    local okt, ft = pcall(function() return string.lower(item:getFullType()) end)
    if not okt then return false end
    local okn, dn = pcall(function() return string.lower(item:getDisplayName()) end)
    dn = okn and dn or ""
    for _, n in ipairs(JUNK_WORDS) do
        if string.find(ft, n, 1, true) or string.find(dn, n, 1, true) then return false end
    end
    for _, n in ipairs(kw.neg) do
        if string.find(ft, n, 1, true) or string.find(dn, n, 1, true) then return false end
    end
    local okc, cat = pcall(function() return string.lower(tostring(item:getCategory())) end)
    cat = okc and cat or ""
    if JUNK_CATS[cat] then return false end
    if kw.util then
        if UTIL_CATS[cat] then return true end
        for _, w in ipairs(UTIL_WORDS) do
            if string.find(ft, w, 1, true) then return true end
        end
    end
    for _, c in ipairs(kw.cats) do
        if cat == c then return true end
    end
    for _, w in ipairs(kw.pos) do
        if string.find(ft, w, 1, true) or string.find(dn, w, 1, true) then return true end
    end
    return false
end

-- Contêiner (armario, geladeira...) ocupa o proprio quadrado: o NPC precisa andar ate um
-- quadrado LIVRE vizinho, senao o pathfinding nao sai do lugar.
local function approachSquare(cell, x, y, z, fromx, fromy)
    local best, bd
    for dx = -1, 1 do
        for dy = -1, 1 do
            if not (dx == 0 and dy == 0) then
                local ok, sq = pcall(function() return cell:getGridSquare(x + dx, y + dy, z) end)
                if ok and sq then
                    local okf, free = pcall(function() return sq:isFree(false) end)
                    if okf and free then
                        local ex, ey = x + dx - fromx, y + dy - fromy
                        local d = ex * ex + ey * ey
                        if not bd or d < bd then best, bd = { x = x + dx, y = y + dy }, d end
                    end
                end
            end
        end
    end
    return best
end

-- lista de contêineres com itens que casam, do mais perto para o mais longe
local function scanContainers(z, kw)
    local out = {}
    local cell = z:getCell()
    local bx, by, bz = math.floor(z:getX()), math.floor(z:getY()), z:getZ()
    for dx = -FETCH_RADIUS, FETCH_RADIUS do
        for dy = -FETCH_RADIUS, FETCH_RADIUS do
            local ok, sq = pcall(function() return cell:getGridSquare(bx + dx, by + dy, bz) end)
            if ok and sq then
                local objs = sq:getObjects()
                for i = 0, objs:size() - 1 do
                    local obj = objs:get(i)
                    local okc, n = pcall(function() return obj:getContainerCount() end)
                    if okc and n and n > 0 then
                        for ci = 0, n - 1 do
                            local cont = obj:getContainerByIndex(ci)
                            if cont then
                                local items = cont:getItems()
                                local hit = 0
                                for k = 0, items:size() - 1 do
                                    if itemMatches(items:get(k), kw) then hit = hit + 1 end
                                end
                                if hit > 0 then
                                    local ap = approachSquare(cell, bx + dx, by + dy, sq:getZ(), bx, by)
                                    out[#out + 1] = { cont = cont, x = bx + dx, y = by + dy, z = sq:getZ(),
                                                      ax = ap and ap.x or (bx + dx), ay = ap and ap.y or (by + dy),
                                                      d2 = dx * dx + dy * dy, hit = hit }
                                end
                            end
                        end
                    end
                end
            end
        end
    end
    table.sort(out, function(a, b) return a.d2 < b.d2 end)
    return out
end

local function finishFetch(bandit, ok, reason)
    local job = fetchJob
    fetchJob = nil
    if job then
        fetchResult = { ok = ok, reason = reason, items = job.taken or {}, label = job.label }
        print(TAG .. "busca terminou: " .. (ok and "ok" or tostring(reason)) .. " (" .. #(job.taken or {}) .. " itens)")
    end
    local player = getSpecificPlayer(0)
    if player and type(BanditMenu) == "table" and type(BanditMenu.SwitchProgram) == "function" then
        pcall(BanditMenu.SwitchProgram, player, bandit, "Companion")
    elseif type(Bandit) == "table" then
        pcall(Bandit.SetProgram, bandit, "Companion", {})
    end
    return { status = true, next = "Prepare", tasks = {} }
end

local function takeFrom(bandit, entry, kw, job)
    local inv = bandit:getInventory()
    local items = entry.cont:getItems()
    local list = {}
    for k = 0, items:size() - 1 do
        local it = items:get(k)
        if it and itemMatches(it, kw) then list[#list + 1] = it end
    end
    for _, it in ipairs(list) do
        if #job.taken >= FETCH_MAX_TAKE then break end
        local name = "item"
        pcall(function() name = it:getDisplayName() end)
        local okr = pcall(function() entry.cont:Remove(it) end)
        if okr then
            pcall(function() inv:AddItem(it) end)
            pcall(function() entry.cont:setDrawDirty(true) end)
            job.taken[#job.taken + 1] = name
        end
    end
end

-- ---- "Ficar aqui" de verdade: nao sai perseguindo, so volta se for empurrado para
-- longe do posto, e vira o rosto pra ameacas proximas (o motor do jogo cuida da luta
-- se o inimigo chegar perto). Baseado no CompanionGuard do proprio Bandits, mas sem
-- exigir um posto de guarda construido no mundo.
ZombiePrograms = ZombiePrograms or {}
ZombiePrograms.CompanionStay = {}
ZombiePrograms.CompanionStay.Stages = {}

ZombiePrograms.CompanionStay.Init = function(bandit)
end

ZombiePrograms.CompanionStay.Prepare = function(bandit)
    Bandit.ForceStationary(bandit, true)
    local brain = BanditBrain.Get(bandit)
    if brain and not brain.ttsPost then
        brain.ttsPost = { x = bandit:getX(), y = bandit:getY(), z = bandit:getZ() }
    end
    return { status = true, next = "Main", tasks = {} }
end

ZombiePrograms.CompanionStay.Wait = function(bandit)
    return { status = true, next = "Main", tasks = {} }
end

ZombiePrograms.CompanionStay.Main = function(bandit)
    local tasks = {}
    local brain = BanditBrain.Get(bandit)
    local post = brain and brain.ttsPost
    if not post then post = { x = bandit:getX(), y = bandit:getY(), z = bandit:getZ() } end

    local dx, dy = post.x - bandit:getX(), post.y - bandit:getY()
    local distPost = math.sqrt(dx * dx + dy * dy)
    if distPost > STAY_LEASH then
        local okW, walkType = pcall(Bandit.GetCombatWalktype, bandit, nil, distPost)
        local okM, task = pcall(BanditUtils.GetMoveTask, 0, post.x, post.y, post.z,
            (okW and walkType) or "Walk", distPost)
        if okM and task then table.insert(tasks, task) end
        return { status = true, next = "Main", tasks = tasks }
    end

    local okZ, closestZombie = pcall(BanditUtils.GetClosestZombieLocation, bandit)
    local okB, closestBandit = pcall(BanditUtils.GetClosestEnemyBanditLocation, bandit)
    local closestEnemy = (okZ and closestZombie) or {}
    if not closestEnemy.dist then closestEnemy.dist = 9999 end
    if okB and closestBandit and closestBandit.dist and closestBandit.dist < closestEnemy.dist then
        closestEnemy = closestBandit
    end

    if closestEnemy.dist and closestEnemy.dist < STAY_NOTICE and closestEnemy.x then
        table.insert(tasks, { action = "FaceLocation", x = closestEnemy.x, y = closestEnemy.y, time = 100 })
    elseif type(BanditPrograms) == "table" and type(BanditPrograms.Idle) == "function" then
        local okI, subTasks = pcall(BanditPrograms.Idle, bandit)
        if okI and type(subTasks) == "table" then
            for _, t in pairs(subTasks) do table.insert(tasks, t) end
        end
    end

    return { status = true, next = "Main", tasks = tasks }
end

ZombiePrograms.CompanionFetch = {}
ZombiePrograms.CompanionFetch.Stages = {}

ZombiePrograms.CompanionFetch.Init = function(bandit)
end

ZombiePrograms.CompanionFetch.Prepare = function(bandit)
    Bandit.ForceStationary(bandit, false)
    return { status = true, next = "Main", tasks = {} }
end

ZombiePrograms.CompanionFetch.Wait = function(bandit)
    return { status = true, next = "Main", tasks = {} }
end

ZombiePrograms.CompanionFetch.Main = function(bandit)
    local job = fetchJob
    if not job then return finishFetch(bandit, false, "none") end
    local t = now()
    if t - job.t0 > FETCH_MAX_MS then return finishFetch(bandit, false, "timeout") end

    -- perigo: um inimigo perto cancela a busca (o Companion cuida da luta)
    -- (GetTarget nao serve: devolve alvo mesmo sem perigo). Contamos zumbis comuns por perto.
    local okT, threats = pcall(countThreats, bandit)
    if okT and type(threats) == "number" and threats >= 2 then
        print(TAG .. "busca cancelada: " .. threats .. " zumbis perto")
        return finishFetch(bandit, false, "danger")
    end

    if not job.targets then
        local okS, list = pcall(scanContainers, bandit, job.kw)
        if not okS then
            print(TAG .. "scan falhou: " .. tostring(list))
            return finishFetch(bandit, false, "none")
        end
        job.targets = list
        job.idx = 1
        job.tTarget = t
        print(TAG .. "busca '" .. tostring(job.label) .. "': " .. #list .. " contêiner(es) com o item")
    end

    local entry = job.targets[job.idx]
    if not entry then
        if #job.taken > 0 then return finishFetch(bandit, true, "ok") end
        return finishFetch(bandit, false, "none")
    end

    local dx, dy = (entry.x + 0.5) - bandit:getX(), (entry.y + 0.5) - bandit:getY()
    local dist = math.sqrt(dx * dx + dy * dy)
    if not entry.logged then
        entry.logged = true
        print(TAG .. "indo ate o contêiner (" .. entry.x .. "," .. entry.y .. "," .. entry.z .. ") via ("
            .. entry.ax .. "," .. entry.ay .. "), dist=" .. math.floor(dist))
    end
    if t - (job.tLog or 0) > 5000 then
        job.tLog = t
        print(TAG .. "busca: dist=" .. string.format("%.1f", dist) .. " alvo " .. job.idx .. "/" .. #job.targets)
    end
    if dist <= 2.2 and math.abs(entry.z - bandit:getZ()) < 0.5 then
        takeFrom(bandit, entry, job.kw, job)
        job.idx = job.idx + 1
        job.tTarget = t
        if #job.taken >= FETCH_MAX_TAKE then return finishFetch(bandit, true, "ok") end
        return { status = true, next = "Main", tasks = {} }
    end
    if t - job.tTarget > 20000 then
        -- nao consegue chegar neste: tenta o proximo
        job.idx = job.idx + 1
        job.tTarget = t
        return { status = true, next = "Main", tasks = {} }
    end

    local tasks = {}
    local okM, task = pcall(BanditUtils.GetMoveTask, 0, entry.ax, entry.ay, entry.z, "Run", dist, false)
    if okM and task then table.insert(tasks, task)
    elseif not okM then print(TAG .. "GetMoveTask falhou: " .. tostring(task)) end
    return { status = true, next = "Main", tasks = tasks }
end

function Adapter.fetch(player, kwcsv, label)
    loadBoard(player)
    local z = findCompanion(player)
    if board or not z then
        print(TAG .. "busca ignorada (sem companheiro visivel)")
        return
    end
    fetchJob = { kw = kwList(kwcsv), label = label ~= "" and label or kwcsv, t0 = now(), taken = {} }
    if type(BanditMenu) == "table" and type(BanditMenu.SwitchProgram) == "function" then
        local ok, err = pcall(BanditMenu.SwitchProgram, player, z, "CompanionFetch")
        if not ok then
            print(TAG .. "falha ao iniciar busca: " .. tostring(err))
            fetchJob = nil
            return
        end
    end
    print(TAG .. "buscando: " .. tostring(fetchJob.label) .. " [" .. tostring(kwcsv) .. "]")
end

-- entrega tudo que o companheiro carrega para o inventario do jogador
local function giveBackpack(playerNum)
    local player = getSpecificPlayer(playerNum)
    local z = player and findCompanion(player)
    if not z then return end
    local moved = {}
    pcall(function()
        local inv, pinv = z:getInventory(), player:getInventory()
        local items = inv:getItems()
        local list = {}
        for i = 0, items:size() - 1 do list[#list + 1] = items:get(i) end
        for _, it in ipairs(list) do
            local name = "item"
            pcall(function() name = it:getDisplayName() end)
            if pcall(function() inv:Remove(it) end) then
                pinv:AddItem(it)
                moved[#moved + 1] = name
            end
        end
    end)
    player:Say(#moved > 0 and ("Recebi " .. #moved .. " item(ns).") or "Ele nao tinha nada.")
    print(TAG .. "entregou " .. #moved .. " itens ao jogador")
end

-- detecta o jogador descendo do veiculo
do
    local wasIn, lastCheck = false, 0
    Events.OnPlayerUpdate.Add(function(player)
        if not player then return end
        local t = now()
        if t - lastCheck < 400 then return end
        lastCheck = t
        local okn, num = pcall(function() return player:getPlayerNum() end)
        if okn and num ~= 0 then return end
        loadBoard(player)
        local inVeh = false
        pcall(function() inVeh = player:getVehicle() ~= nil end)
        if inVeh then wasSeenInVehicle = true end
        if board and not pending then
            if wasIn and not inVeh then
                unboardCompanion(player)
            elseif not inVeh and not wasSeenInVehicle and t - boardedAt > NOVEHICLE_TIMEOUT_MS then
                print(TAG .. "nao entrou em veiculo a tempo; desembarcando")
                unboardCompanion(player)
            end
        end
        wasIn = inVeh
    end)
    if Events.OnExitVehicle then
        Events.OnExitVehicle.Add(function(chr)
            local player = getSpecificPlayer(0)
            if player and chr == player and board and not pending then unboardCompanion(player) end
        end)
    end
end

-- ---- Eventos pontuais (comparando com o estado anterior) --------------------------
local last = { hp = nil, ammo = nil, had = false, miss = 0, z = nil, alerted = false }

-- Diagnostico: se o companheiro ficou HOSTIL (ex.: friendly fire), avisa no console
-- em vez de fingir que ele "morreu".
local function checkTurnedHostile()
    local z = last.z
    if not z then return false end
    local ok, dead = pcall(function() return z:isDead() end)
    if not ok or dead then return false end
    local b = brainOf(z)
    if b and (b.hostile or b.hostileP) then
        if not last.alerted then
            last.alerted = true
            print(TAG .. "ALERTA: o companheiro ficou HOSTIL (hostile=" .. tostring(b.hostile)
                .. ", hostileP=" .. tostring(b.hostileP) .. ", programa="
                .. tostring(b.program and b.program.name) .. ")")
        end
        return true
    end
    return false
end

local function tickReveal(player)
    if not revealJob then return end
    local t = now()
    if t < revealJob.t then return end
    local z = findCompanion(player)
    local mode = revealJob.mode
    revealJob = nil
    if not z then
        print(TAG .. "companheiro sumiu antes de reaparecer")
        return
    end
    local x, y, zz = freeSpotNear(player)
    moveTo(z, x, y, zz)
    setHidden(z, false)
    currentMode = "seguir"
    if mode and mode ~= "seguir" then
        Adapter.setMode(player, mode)
    elseif type(BanditMenu) == "table" and type(BanditMenu.SwitchProgram) == "function" then
        pcall(BanditMenu.SwitchProgram, player, z, "Companion")
    end
    print(TAG .. "companheiro reapareceu")
end

function Adapter.pollEvents(player)
    local ev = {}
    loadBoard(player)
    tickReveal(player)
    if pending then applyPending(player) end
    if fetchResult then
        local r = fetchResult
        fetchResult = nil
        if r.ok and #r.items > 0 then
            ev[#ev + 1] = { evt = "loot", payload = "item=" .. tostring(r.items[1]) }
        else
            ev[#ev + 1] = { evt = "fetch_fail", payload = "reason=" .. tostring(r.reason or "none") }
        end
    end
    local z = findCompanion(player)
    if not z and (board or pending) then
        last.had, last.miss = true, 0
        return ev
    end
    if not z then
        if last.had and checkTurnedHostile() then return ev end
        if last.had then
            last.miss = last.miss + 1
            if last.miss >= 6 then
                ev[#ev + 1] = { evt = "died", payload = "" }
                last.had, last.hp, last.ammo, last.miss = false, nil, nil, 0
            end
        end
        return ev
    end
    last.had, last.miss, last.z, last.alerted = true, 0, z, false

    local hp = readHp(z)
    if last.hp and hp <= last.hp - 5 then
        ev[#ev + 1] = { evt = "hurt", payload = "amount=" .. (last.hp - hp) }
    end
    last.hp = hp

    local ammo = readAmmo(z)
    if last.ammo and last.ammo ~= "empty" and ammo == "empty" then
        ev[#ev + 1] = { evt = "no_ammo", payload = "" }
    end
    last.ammo = ammo
    return ev
end

-- ---- Menu: chamar o companheiro ----------------------------------------------------
Events.OnFillWorldObjectContextMenu.Add(function(playerNum, context, worldobjects, test)
    if test then return end
    local player = getSpecificPlayer(playerNum)
    if not player then return end
    loadBoard(player)
    if board or pending then
        context:addOption("Companheiro: desembarcar", playerNum, function(n)
            unboardCompanion(getSpecificPlayer(n))
        end)
        context:addOption("Companheiro: ver mochila", playerNum, showBackpack)
    elseif findCompanion(player) then
        context:addOption("Companheiro: entrar no carro", playerNum, boardCompanion)
        context:addOption("Companheiro: ver mochila", playerNum, showBackpack)
        context:addOption("Companheiro: pegar itens dele", playerNum, giveBackpack)
    else
        context:addOption("Companheiro: chamar (Bandits)", playerNum, spawnCompanion)
    end
end)
Events.OnGameStart.Add(silenceBandits)

NPC_Bridge.registerAdapter(Adapter)
print(TAG .. "adapter registrado")