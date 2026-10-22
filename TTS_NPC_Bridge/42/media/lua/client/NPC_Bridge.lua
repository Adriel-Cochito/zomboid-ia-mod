-- =====================================================================
-- TTS NPC Bridge (núcleo)
-- Troca de mensagens com o daemon externo (Rust/Python) por arquivos de texto:
--   Lua    -> daemon : NPC_events.txt    (evento|payload)
--   daemon -> Lua    : NPC_commands.txt  (seq|tipo|arg|extra)
-- NÃO contém lógica de NPC: quem conhece o mod base é o ADAPTER
-- (ex.: NPC_AdapterStub.lua). Trocar de mod = trocar só o adapter.
-- =====================================================================
NPC_Bridge = NPC_Bridge or {}

local EVENTS_FILE   = "NPC_events.txt"
local COMMANDS_FILE = "NPC_commands.txt"

local POLL_COMMANDS_TICKS = 60    -- ~1 s
local POLL_EVENTS_TICKS   = 30    -- ~0,5 s
local EMIT_STATE_TICKS    = 300   -- ~5 s

NPC_Bridge.adapter = nil

-- Contrato do adapter (todas as funções recebem o 'player' local):
--   name                           string
--   hasNpc(player)            -> bool
--   isNpcNearby(player, objs) -> bool          (para mostrar o menu)
--   npcName(player)           -> string
--   getState(player)          -> {name,mode,hp,player_hp,threats,ammo,loot_near}
--   setMode(player, mode)                      (mode: seguir|ficar|defender|saquear)
--   say(player, text)                          (legenda/balão da fala)
--   pollEvents(player)        -> { {evt="kill", payload="total=3"}, ... }  (opcional)
function NPC_Bridge.registerAdapter(adapter)
    NPC_Bridge.adapter = adapter
    print("[TTS NPC] Adapter registrado: " .. tostring(adapter and adapter.name))
end

-- ---------------------------------------------------------------- utilidades
local function cleanKV(v)
    return (tostring(v == nil and "" or v):gsub("[|;=\r\n]", " "))
end

local function cleanText(v)
    return (tostring(v == nil and "" or v):gsub("[|\r\n]", " "))
end

function NPC_Bridge.kv(t)
    local keys = {}
    for k in pairs(t) do keys[#keys + 1] = k end
    table.sort(keys)
    local parts = {}
    for _, k in ipairs(keys) do
        parts[#parts + 1] = k .. "=" .. cleanKV(t[k])
    end
    return table.concat(parts, ";")
end

local reportedEmitError = false
function NPC_Bridge.emit(evt, payload)
    local ok, err = pcall(function()
        local w = getFileWriter(EVENTS_FILE, true, true)   -- cria se não existir, modo append
        w:write(evt .. "|" .. (payload or "") .. "\n")
        w:close()
    end)
    if not ok and not reportedEmitError then
        reportedEmitError = true
        print("[TTS NPC] ERRO ao gravar evento: " .. tostring(err))
    end
end
local emit = NPC_Bridge.emit

local disabled = {}
local function safe(name, fn, ...)
    if disabled[name] then return end
    local ok, err = pcall(fn, ...)
    if not ok then
        disabled[name] = true
        print("[TTS NPC] ERRO em " .. name .. " (checagem DESATIVADA): " .. tostring(err))
    end
end

-- ---------------------------------------------------------------- comandos (daemon -> Lua)
local lastSeq = nil

local function readCommandLines()
    local reader = getFileReader(COMMANDS_FILE, true)
    if not reader then return {} end
    local lines = {}
    local line = reader:readLine()
    while line do
        lines[#lines + 1] = line
        line = reader:readLine()
    end
    reader:close()
    return lines
end

local function handleCommand(player, cmd)
    local adapter = NPC_Bridge.adapter
    if not adapter then return end
    if cmd.kind == "mode" and adapter.setMode then
        print("[TTS NPC] modo -> " .. cmd.arg .. " (" .. cmd.extra .. ")")
        adapter.setMode(player, cmd.arg)
    elseif cmd.kind == "say" and adapter.say then
        adapter.say(player, cmd.arg)
    elseif cmd.kind == "fetch" and adapter.fetch then
        print("[TTS NPC] buscar -> " .. cmd.arg .. " (" .. cmd.extra .. ")")
        adapter.fetch(player, cmd.arg, cmd.extra)
    end
end

local function pollCommands(player)
    local cmds, maxSeq = {}, 0
    for _, line in ipairs(readCommandLines()) do
        local seq, kind, arg, extra = string.match(line, "^(%d+)|([^|]*)|([^|]*)|?(.*)$")
        if seq then
            seq = tonumber(seq)
            cmds[#cmds + 1] = { seq = seq, kind = kind, arg = arg, extra = extra }
            if seq > maxSeq then maxSeq = seq end
        end
    end

    if lastSeq == nil then          -- 1ª leitura: ignora comandos de sessões antigas
        lastSeq = maxSeq
        return
    end
    if maxSeq < lastSeq then lastSeq = 0 end   -- daemon reiniciado

    for _, cmd in ipairs(cmds) do
        if cmd.seq > lastSeq then
            lastSeq = cmd.seq
            safe("handleCommand", handleCommand, player, cmd)
        end
    end
end

-- ---------------------------------------------------------------- eventos (Lua -> daemon)
local hadNpc = false

local function emitState(player)
    local adapter = NPC_Bridge.adapter
    if not adapter then return end

    local has = adapter.hasNpc(player)
    if has and not hadNpc then
        emit("joined", "name=" .. cleanKV(adapter.npcName and adapter.npcName(player) or "Companheiro"))
    elseif hadNpc and not has then
        emit("left", "")
    end
    hadNpc = has
    if not has then return end

    local st = adapter.getState(player)
    if st then emit("state", NPC_Bridge.kv(st)) end
end

local function emitAdapterEvents(player)
    local adapter = NPC_Bridge.adapter
    if not adapter or not adapter.pollEvents or not hadNpc then return end
    local list = adapter.pollEvents(player)
    if not list then return end
    for _, e in ipairs(list) do
        emit(e.evt, e.payload or "")
    end
end

-- ---------------------------------------------------------------- menu de contexto (botão direito)
local function onTextBoxDone(target, button)
    if button.internal == "OK" then
        local text = button.parent.entry:getText()
        if text and text ~= "" then
            emit("say", cleanText(text))
        end
    end
end

function NPC_Bridge.askText(playerNum)
    local ok, err = pcall(function()
        local w, h = 320, 180
        local x = getCore():getScreenWidth() / 2 - w / 2
        local y = getCore():getScreenHeight() / 2 - h / 2
        local modal = ISTextBox:new(x, y, w, h, "Falar com o companheiro:", "", nil, onTextBoxDone, playerNum)
        modal:initialise()
        modal:addToUIManager()
    end)
    if not ok then print("[TTS NPC] ERRO ao abrir caixa de texto: " .. tostring(err)) end
end

local function onFillWorldObjectContextMenu(playerNum, context, worldobjects, test)
    if test then return end
    local adapter = NPC_Bridge.adapter
    if not adapter then return end
    local player = getSpecificPlayer(playerNum)
    if not player or not hadNpc then return end
    if not adapter.isNpcNearby(player, worldobjects) then return end

    local name = adapter.npcName and adapter.npcName(player) or "Companheiro"
    local option = context:addOption("Companheiro: " .. name, worldobjects, nil)
    local sub = ISContextMenu:getNew(context)
    context:addSubMenu(option, sub)

    sub:addOption("Seguir",   player, function() emit("cmd", "seguir") end)
    sub:addOption("Ficar aqui", player, function() emit("cmd", "ficar") end)
    sub:addOption("Defender", player, function() emit("cmd", "defender") end)
    sub:addOption("Buscar itens úteis",  player, function() emit("cmd", "saquear") end)
    sub:addOption("Falar...", playerNum, NPC_Bridge.askText)
end

-- ---------------------------------------------------------------- loop principal
local tick = 0
local function onPlayerUpdate(player)
    if not player or not player:isLocalPlayer() then return end
    tick = tick + 1
    if tick % POLL_COMMANDS_TICKS == 0 then safe("pollCommands", pollCommands, player) end
    if tick % POLL_EVENTS_TICKS == 0   then safe("emitAdapterEvents", emitAdapterEvents, player) end
    if tick % EMIT_STATE_TICKS == 0    then safe("emitState", emitState, player) end
end

-- ---------------------------------------------------------- pausa do jogo
-- O daemon externo continua rodando (e falando) mesmo com o jogo pausado, porque
-- ele nao sabe nada sobre o estado do PZ. Por isso avisamos explicitamente, usando
-- um gancho que roda mesmo em pausa (OnTickEvenPaused), se o jogo tiver esse evento.
local lastPauseCheckMs = 0
local isPausedNow = false
local function checkPause()
    local t = getTimestampMs and getTimestampMs() or 0
    if t - lastPauseCheckMs < 250 then return end
    lastPauseCheckMs = t
    local ok, speed = pcall(getGameSpeed)
    if not ok then return end -- API indisponivel nesta build: nao quebra nada, so nao detecta pausa
    local paused = (speed == 0)
    if paused ~= isPausedNow then
        isPausedNow = paused
        emit(paused and "paused" or "resumed", "")
    end
end
if Events.OnTickEvenPaused then
    Events.OnTickEvenPaused.Add(checkPause)
else
    -- fallback: so detecta a volta da pausa (o proprio pollar ja nao roda pausado)
    Events.OnPlayerUpdate.Add(checkPause)
end

Events.OnPlayerUpdate.Add(onPlayerUpdate)
Events.OnFillWorldObjectContextMenu.Add(onFillWorldObjectContextMenu)

print("[TTS NPC] Ponte do NPC carregada (v1). Aguardando adapter...")