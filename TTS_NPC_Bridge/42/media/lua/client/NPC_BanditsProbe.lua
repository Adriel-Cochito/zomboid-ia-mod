-- =====================================================================
-- SONDA v2 do Bandits (temporaria). SUBSTITUI a v1 (mesmo nome de arquivo).
-- Uso: botao direito no chao -> "TTS: sonda do Bandits v2"
-- Gera Zomboid\Lua\NPC_probe2.txt. So LE dados; nao altera nada no jogo.
-- Responde: existem bandits no mundo? onde? qual programa/mestre? quais clas
-- existem e sao amigaveis? como o mod cria (spawn) e comanda companheiros?
-- =====================================================================
local PROBE_FILE = "NPC_probe2.txt"
local MAX_KEYS = 40
local MAX_ITEMS = 15

local lines = {}
local function out(s) lines[#lines + 1] = tostring(s) end
local function section(t) out(""); out("=== " .. t .. " ===") end

local function simple(v)
    local t = type(v)
    if t == "string" or t == "number" or t == "boolean" then
        local s = tostring(v)
        if #s > 80 then s = string.sub(s, 1, 80) .. "..." end
        return s
    end
    return "<" .. t .. ">"
end

local function sortedKeys(t)
    local keys = {}
    for k in pairs(t) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    return keys
end

local function dumpTable(t, depth, maxDepth, indent)
    local keys = sortedKeys(t)
    for i, k in ipairs(keys) do
        if i > MAX_KEYS then out(indent .. "... (+" .. (#keys - MAX_KEYS) .. ")"); break end
        local v = t[k]
        if type(v) == "table" and depth < maxDepth then
            out(indent .. tostring(k) .. " = {table}")
            dumpTable(v, depth + 1, maxDepth, indent .. "  ")
        else
            out(indent .. tostring(k) .. " = " .. simple(v))
        end
    end
end

local function listKeys(label, t)
    if type(t) ~= "table" then out(label .. ": (nao existe)"); return end
    out(label .. ":")
    local keys = sortedKeys(t)
    for i, k in ipairs(keys) do
        if i > 80 then out("    ... (+" .. (#keys - 80) .. ")"); break end
        out("    " .. tostring(k) .. " : " .. type(t[k]))
    end
end

local function step_apis()
    section("API: chaves de tabelas importantes")
    listKeys("BanditServer.Spawner", BanditServer and BanditServer.Spawner)
    listKeys("BanditServer.Commands", BanditServer and BanditServer.Commands)
    listKeys("BanditServer.Players", BanditServer and BanditServer.Players)
    listKeys("ZombiePrograms.Companion", ZombiePrograms and ZombiePrograms.Companion)
    listKeys("ZombiePrograms.CompanionGuard", ZombiePrograms and ZombiePrograms.CompanionGuard)
    listKeys("ZombiePrograms.Defend", ZombiePrograms and ZombiePrograms.Defend)
    listKeys("ZombiePrograms.Looter", ZombiePrograms and ZombiePrograms.Looter)
    listKeys("BanditPlayer", BanditPlayer)
    listKeys("BanditUtils", BanditUtils)
    listKeys("BanditCustom", BanditCustom)
end

local function step_sandbox()
    section("SandboxVars.Bandits")
    if SandboxVars and type(SandboxVars.Bandits) == "table" then
        dumpTable(SandboxVars.Bandits, 1, 1, "  ")
    else
        out("  SandboxVars.Bandits nao existe")
    end
end

local function step_clans()
    section("CLAS (BanditCustom.ClanGetAll)")
    if not (BanditCustom and type(BanditCustom.ClanGetAll) == "function") then out("  sem ClanGetAll"); return end
    local ok, all = pcall(BanditCustom.ClanGetAll)
    if not ok or type(all) ~= "table" then out("  ClanGetAll falhou"); return end
    local n = 0
    for id, clan in pairs(all) do
        n = n + 1
        if n > 12 then out("  ... mais clas omitidos"); break end
        out("  clan " .. tostring(id))
        if type(clan) == "table" then dumpTable(clan, 1, 2, "    ") end
    end
    out("  (total listado: " .. math.min(n, 12) .. ")")
end

local function step_global(player)
    section("BANDITS NO MUNDO (BanditGlobalData)")
    local gd = BanditGlobalData
    if type(gd) ~= "table" then out("  BanditGlobalData nao existe"); return end
    local px, py = player:getX(), player:getY()
    for _, name in ipairs({ "Bandits", "Wanderers" }) do
        local t = gd[name]
        if type(t) == "table" then
            local total, shown = 0, 0
            for id, rec in pairs(t) do
                total = total + 1
                if shown < MAX_ITEMS then
                    shown = shown + 1
                    out("  " .. name .. "[" .. tostring(id) .. "]")
                    if type(rec) == "table" then dumpTable(rec, 1, 2, "    ") else out("    " .. simple(rec)) end
                end
            end
            out("  total em " .. name .. ": " .. total)
        else
            out("  " .. name .. ": (nao e tabela)")
        end
    end
    out("  jogador em: " .. string.format("%.0f,%.0f", px, py))
end

local function step_zombies(player)
    section("ZUMBIS COM CEREBRO DE BANDIT (raio 150)")
    local cell = player:getCell()
    local list = cell and cell:getZombieList()
    if not list then out("  sem lista"); return end
    local px, py = player:getX(), player:getY()
    local seen, with = 0, 0
    for i = 0, list:size() - 1 do
        local z = list:get(i)
        if z then
            seen = seen + 1
            local dx, dy = z:getX() - px, z:getY() - py
            if dx * dx + dy * dy <= 150 * 150 then
                local ok, brain = pcall(function() return BanditBrain.Get(z) end)
                if ok and type(brain) == "table" and with < MAX_ITEMS then
                    with = with + 1
                    out("-- bandit a " .. string.format("%.1f", math.sqrt(dx * dx + dy * dy)) .. " tiles")
                    pcall(function() out("  nome: " .. tostring(z:getDisplayName())) end)
                    dumpTable(brain, 1, 1, "    ")
                    local okh, h = pcall(function() return Bandit.IsHostile(z) end)
                    out("    IsHostile = " .. tostring(okh and h))
                    local okm, m = pcall(function() return Bandit.GetMaster(z) end)
                    out("    GetMaster = " .. (okm and simple(m) or "erro"))
                    local okp, p = pcall(function() return Bandit.GetProgram(z) end)
                    out("    GetProgram = " .. (okp and (type(p) == "table" and "{table}" or simple(p)) or "erro"))
                    if okp and type(p) == "table" then dumpTable(p, 1, 1, "      ") end
                end
            end
        end
    end
    out("  zumbis carregados: " .. seen .. " | com cerebro Bandit: " .. with)
end

local function runProbe(playerNum)
    lines = {}
    local player = getSpecificPlayer(playerNum)
    out("TTS NPC probe v2")
    local steps = {
        step_global, step_zombies, step_clans, step_sandbox, step_apis,
    }
    for _, step in ipairs(steps) do
        local ok, err = pcall(step, player)
        if not ok then out("ERRO no passo: " .. tostring(err)) end
    end
    local ok, err = pcall(function()
        local w = getFileWriter(PROBE_FILE, true, false)
        for _, l in ipairs(lines) do w:write(l .. "\n") end
        w:close()
    end)
    for _, l in ipairs(lines) do print("[TTS PROBE2] " .. l) end
    pcall(function() player:Say("Sonda v2 concluida: NPC_probe2.txt") end)
    if not ok then print("[TTS PROBE2] ERRO ao gravar: " .. tostring(err)) end
end

Events.OnFillWorldObjectContextMenu.Add(function(playerNum, context, worldobjects, test)
    if test then return end
    context:addOption("TTS: sonda do Bandits v2", playerNum, runProbe)
end)
print("[TTS PROBE2] carregada: botao direito no chao -> 'TTS: sonda do Bandits v2'")