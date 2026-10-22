-- =====================================================================
-- Adapter de TESTE: um companheiro "virtual" derivado do próprio jogador.
-- Serve para validar a ponte inteira (menu, texto, voz, decisão de modo)
-- sem nenhum mod de NPC instalado. Não move nenhum NPC de verdade:
--   * vida do NPC = 100 fixa; ameaças = zumbis mirando em você a <= 10 tiles
--   * "kill" é emitido quando SEUS abates sobem; "hurt" quando SUA vida cai
--   * setMode só guarda o modo e escreve no console.txt
--   * say usa o balão de fala do seu personagem
-- Para um NPC real, copie docs\NPC_AdapterTemplate.lua.txt e implemente as funções.
-- =====================================================================
require "NPC_Bridge"

local Stub = {
    name = "stub (virtual)",
    mode = "seguir",
    lastKills = nil,
    lastHealth = nil,
}

local function countThreats(player)
    local cell = player:getCell()
    local list = cell and cell:getZombieList()
    if not list then return 0 end
    local px, py = player:getX(), player:getY()
    local n = 0
    for i = 0, list:size() - 1 do
        local z = list:get(i)
        if z and z:getTarget() == player then
            local dx, dy = z:getX() - px, z:getY() - py
            if dx * dx + dy * dy <= 100 then n = n + 1 end
        end
    end
    return n
end

function Stub.hasNpc(player) return true end
function Stub.isNpcNearby(player, worldobjects) return true end
function Stub.npcName(player) return "Marcos" end

function Stub.getState(player)
    local bd = player:getBodyDamage()
    local playerHp = bd and math.floor(bd:getOverallBodyHealth()) or 100
    return {
        name = "Marcos",
        mode = Stub.mode,
        hp = 100,
        player_hp = playerHp,
        threats = countThreats(player),
        ammo = "ok",
        loot_near = 0,
    }
end

function Stub.setMode(player, mode)
    Stub.mode = mode
    print("[TTS NPC STUB] modo do companheiro virtual -> " .. tostring(mode))
end

function Stub.say(player, text)
    pcall(function() player:Say(text) end)
end

function Stub.pollEvents(player)
    local events = {}

    local kills = player:getZombieKills()
    if Stub.lastKills ~= nil and kills > Stub.lastKills then
        events[#events + 1] = { evt = "kill", payload = "total=" .. kills }
    end
    Stub.lastKills = kills

    local bd = player:getBodyDamage()
    if bd then
        local hp = bd:getOverallBodyHealth()
        if Stub.lastHealth ~= nil and (Stub.lastHealth - hp) >= 3 then
            events[#events + 1] = { evt = "hurt", payload = "amount=" .. math.floor(Stub.lastHealth - hp) }
        end
        Stub.lastHealth = hp
    end
    return events
end

local ENABLE_STUB = false   -- true só para testar a ponte sem NPC real
if ENABLE_STUB then NPC_Bridge.registerAdapter(Stub) end