local TTSEvents = {}

-- Estado e cooldowns (em milissegundos de tempo REAL)
local lastZombieAlertMs = 0
local lastHurtMs = 0
local lastRestAlertMs = 0
local lastPanicAlertMs = 0
local lastExhaustionAlertMs = 0
local lastCombatAlertMs = 0
local lastHungerAlertMs = 0
local lastThirstAlertMs = 0
local lastBoredomAlertMs = 0
local lastSickAlertMs = 0
local lastStealthAlertMs = 0
local lastJammedAlertMs = 0
local lastAmmoAlertMs = 0
local lastVehicleAlertMs = 0
local lastSoakedAlertMs = 0
local lastLootAlertMs = 0
local lastBleedingAlertMs = 0

local lastHealth = nil
local lastWounds = nil
local lastPanicLevel = 0
local lastExhaustionLevel = 0
local lastInventoryCount = nil  -- nil: ignora a 1a leitura (senão dispara ao carregar)
local lastZombieKills = nil
local wasAsleep = false
local wasJammed = false
local wasInVehicle = false
local wasBleeding = false
local lastHungerLevelValue = 0
local wasResting = false

local isRainingState = false
local tickCounter = 0
local reportedErrors = {}

local function nowMs()
    return getTimestampMs()
end

local disabledChecks = {}
local function safe(name, fn, ...)
    if disabledChecks[name] then return end
    local ok, err = pcall(fn, ...)
    if not ok then
        disabledChecks[name] = true
        print("[TTS MOD] ERRO em " .. name .. " (checagem DESATIVADA): " .. tostring(err))
    end
end

local function callIfExists(obj, methodName)
    if obj == nil or obj[methodName] == nil then return nil end
    return obj[methodName](obj)
end

local function emit(eventName, detail)
    local d = (tostring(detail or ""):gsub("[|\r\n]", " "))
    local ok, err = pcall(function()
        local w = getFileWriter("TTS_events.txt", true, true)
        w:write(eventName .. "|" .. d .. "\n")
        w:close()
    end)
    if not ok and not reportedErrors["emit"] then
        reportedErrors["emit"] = true
        print("[TTS MOD] ERRO ao gravar evento: " .. tostring(err))
    end
end

-- -------------------------------------------------------------
-- EVENTO 1: Zumbi vindo por trás / Indoor
-- -------------------------------------------------------------
function TTSEvents.checkBehindZombie(player)
    local t = nowMs()
    if t - lastZombieAlertMs < 5000 then return end

    local zombieList = player:getCell():getZombieList()
    if not zombieList then return end
    local dir = player:getForwardDirection()
    local px, py = player:getX(), player:getY()
    local isOutside = player:isOutside()

    for i = 0, zombieList:size() - 1 do
        local zombie = zombieList:get(i)
        if zombie and zombie:getTarget() == player then
            local dx = zombie:getX() - px
            local dy = zombie:getY() - py
            local distSq = dx * dx + dy * dy

            if distSq <= 16 then
                local dot = (dir:getX() * dx) + (dir:getY() * dy)
                if dot < -0.3 then
                    if isOutside then
                        emit("zombie_back", "rua")
                    else
                        emit("zombie_indoor", "casa")
                    end
                    lastZombieAlertMs = t
                    break
                end
            end
        end
    end
end

-- -------------------------------------------------------------
-- EVENTO 2: Jogador ferido
-- -------------------------------------------------------------
local function fireHurt(reason, detail)
    local t = nowMs()
    if t - lastHurtMs < 3000 then return end
    lastHurtMs = t
    emit("hurt", reason)
end

function TTSEvents.checkWounds(player)
    local bd = player:getBodyDamage()
    if not bd then return end
    local bitten = callIfExists(bd, "getNumPartsBitten")
    local scratched = callIfExists(bd, "getNumPartsScratched")
    
    local wounds = (bitten or 0) + (scratched or 0)
    if lastWounds ~= nil and wounds > lastWounds then
        fireHurt("novo ferimento", wounds - lastWounds)
    end
    lastWounds = wounds
end

function TTSEvents.checkHealth(player)
    local bd = player:getBodyDamage()
    if not bd then return end
    local current = bd:getOverallBodyHealth()
    if lastHealth ~= nil and (lastHealth - current) >= 3 then
        fireHurt("vida caiu", string.format("%.1f", lastHealth - current))
    end
    lastHealth = current
end

-- -------------------------------------------------------------
-- EVENTO EXTRA: Sangramento Ativo e Resolvido
-- -------------------------------------------------------------
function TTSEvents.checkBleeding(player)
    local bd = player:getBodyDamage()
    if not bd then return end
    local bodyParts = bd:getBodyParts()
    if not bodyParts then return end

    local isBleeding = false
    for i = 0, bodyParts:size() - 1 do
        local part = bodyParts:get(i)
        if part and part:bleeding() then
            isBleeding = true
            break
        end
    end

    local t = nowMs()
    if isBleeding and (t - lastBleedingAlertMs > 35000) then
        emit("bleeding", "sangrando")
        lastBleedingAlertMs = t
    end
    
    if wasBleeding and not isBleeding then
        if t - lastBleedingAlertMs > 30000 then
            emit("bleeding_resolved", "estancou")
            lastBleedingAlertMs = t
        end
    end
    
    wasBleeding = isBleeding
end

-- -------------------------------------------------------------
-- EVENTO 3: Chuva forte
-- -------------------------------------------------------------
function TTSEvents.checkWeather()
    local climate = getClimateManager()
    if not climate then return end
    local isRaining = climate:isRaining()
    local intensity = climate:getRainIntensity()

    if isRaining and intensity > 0.4 and not isRainingState then
        isRainingState = true
        emit("rain", string.format("%.2f", intensity))
    elseif not isRaining and isRainingState then
        isRainingState = false
    end
end

-- -------------------------------------------------------------
-- SNAPSHOT DO PERSONAGEM (enviado junto do evento "rest")
-- Formato: profession=Cozinheiro;days=12;hours=290;Cooking=3;Aiming=2
-- -------------------------------------------------------------
local TRACKED_PERKS = {
    "Axe", "Blunt", "SmallBlunt", "LongBlade", "SmallBlade", "Spear", "Maintenance",
    "Aiming", "Reload", "Sneaking", "Lightfooted", "Nimble", "Fitness", "Strength",
    "Cooking", "Farming", "Doctor", "Woodwork", "Mechanics", "Electricity",
    "MetalWelding", "Tailoring", "Fishing", "Trapping", "PlantScavenging",
}

local function cleanField(v)
    return (tostring(v):gsub("[;=|\r\n]", " "))
end

local function getProfessionName(player)
    local desc = player:getDescriptor()
    if desc == nil then return nil end

    local raw = callIfExists(desc, "getCharacterProfession")
    if raw == nil then raw = callIfExists(desc, "getProfession") end
    if raw == nil then return nil end

    if type(raw) ~= "string" then
        local n = callIfExists(raw, "getName") or callIfExists(raw, "getUIName")
        if n then return n end
        return tostring(raw)
    end

    if ProfessionFactory ~= nil and ProfessionFactory.getProfession ~= nil then
        local p = ProfessionFactory.getProfession(raw)
        if p ~= nil then
            local n = callIfExists(p, "getName")
            if n then return n end
        end
    end
    return raw
end

local function buildPlayerStatus(player)
    local parts = {}

    local ok, prof = pcall(getProfessionName, player)
    if ok and prof then
        parts[#parts + 1] = "profession=" .. cleanField(prof)
    end

    local hours = callIfExists(player, "getHoursSurvived")
    if hours then
        parts[#parts + 1] = "days=" .. math.floor(hours / 24)
        parts[#parts + 1] = "hours=" .. math.floor(hours)
    end

    for _, name in ipairs(TRACKED_PERKS) do
        local okPerk, level = pcall(function()
            local perk = Perks[name]
            if perk == nil then return nil end
            return player:getPerkLevel(perk)
        end)
        if okPerk and level and level > 0 then
            parts[#parts + 1] = name .. "=" .. level
        end
    end

    return table.concat(parts, ";")
end


-- -------------------------------------------------------------
-- EVENTO 4: Descanso / Cama e Acordar (wake_up)
-- -------------------------------------------------------------
function TTSEvents.checkResting(player)
    local sleeping = player:isAsleep()
    local resting = callIfExists(player, "isResting") == true
    local isCurrentResting = sleeping or resting

    -- Entrou em descanso ou foi dormir pela primeira vez
    if isCurrentResting and not wasResting then
            emit("rest", buildPlayerStatus(player))
        
    -- Acordou ou levantou do descanso
    elseif not isCurrentResting and wasResting then
        emit("wake_up", "acordou")
    end

    wasResting = isCurrentResting
end

-- -------------------------------------------------------------
-- EVENTO 5: Moodles (Completo e Consolidado)
-- -------------------------------------------------------------
local moodleCandidates = {
    panic      = {"Panic", "PANIC"},
    exhaustion = {"Endurance", "ENDURANCE"},
    wet        = {"Wet", "WET"},
    hunger     = {"Hungry", "HUNGRY", "Hunger"},
    thirst     = {"Thirst", "THIRST", "Thirsty"},
    bored      = {"Bored", "BORED", "Boredom"},
    unhappy    = {"Unhappy", "UNHAPPY", "Unhappiness"},
    sick       = {"Sick", "SICK", "FoodSickness", "Sickness"},
}
local moodleTypes = nil
local moodleOff = {}

local function resolveMoodleTypes()
    moodleTypes = {}
    local report = {}
    for key, names in pairs(moodleCandidates) do
        local found = nil
        if MoodleType ~= nil then
            for _, n in ipairs(names) do
                local ok, v = pcall(function() return MoodleType[n] end)
                if ok and v ~= nil then found = v; break end
            end
        end
        moodleTypes[key] = found
        report[#report + 1] = key .. "=" .. (found ~= nil and "ok" or "AUSENTE")
    end
    table.sort(report)
    print("[TTS MOD] Moodles resolvidos: " .. table.concat(report, " "))
end

local function countNearbyZombies(player, tiles)
    local list = player:getCell() and player:getCell():getZombieList()
    if not list then return 0 end
    local px, py = player:getX(), player:getY()
    local maxSq = tiles * tiles
    local n = 0
    for i = 0, list:size() - 1 do
        local z = list:get(i)
        if z then
            local dead = false
            pcall(function() dead = z:isDead() end)
            if not dead then
                local dx, dy = z:getX() - px, z:getY() - py
                if dx * dx + dy * dy <= maxSq then n = n + 1 end
            end
        end
    end
    return n
end

local function moodleLevel(moodles, key)
    if moodleOff[key] then return 0 end
    local mt = moodleTypes[key]
    if mt == nil then return 0 end
    local ok, level = pcall(function() return moodles:getMoodleLevel(mt) end)
    if not ok or level == nil then
        moodleOff[key] = true
        print("[TTS MOD] moodle '" .. key .. "' DESATIVADO (getMoodleLevel falhou)")
        return 0
    end
    return level
end

function TTSEvents.checkMoodles(player)
    local t = nowMs()
    local moodles = player:getMoodles()
    if not moodles then return end
    if moodleTypes == nil then resolveMoodleTypes() end

    local panic = moodleLevel(moodles, "panic")
    if panic >= 1 and (t - lastPanicAlertMs > 25000) then
        local lugar = player:isOutside() and "rua" or "casa"
        emit("panic", "nivel_" .. panic .. ";lugar=" .. lugar .. ";zumbis=" .. countNearbyZombies(player, 6))
        lastPanicAlertMs = t
    end

    local exhaustion = moodleLevel(moodles, "exhaustion")
    if exhaustion >= 2 and (t - lastExhaustionAlertMs > 30000) then
        emit("exhaustion", "nivel_" .. exhaustion)
        lastExhaustionAlertMs = t
    end

    local wet = moodleLevel(moodles, "wet")
    if wet >= 3 and (t - lastSoakedAlertMs > 60000) then
        emit("soaked", "encharcado")
        lastSoakedAlertMs = t
    end

    -- Fome e Fome Saciada
    local hunger = moodleLevel(moodles, "hunger")
    if hunger >= 1 and lastHungerLevelValue == 0 then
        emit("hunger", "nivel_" .. hunger)
        lastHungerAlertMs = t
    elseif hunger == 0 and lastHungerLevelValue >= 1 then
        if t - lastHungerAlertMs > 30000 then
            emit("hunger_resolved", "saciado")
            lastHungerAlertMs = t
        end
    end
    lastHungerLevelValue = hunger

    local thirst = moodleLevel(moodles, "thirst")
    if thirst >= 2 and (t - lastThirstAlertMs > 40000) then
        emit("thirst", "nivel_" .. thirst)
        lastThirstAlertMs = t
    end

    local boredom = moodleLevel(moodles, "bored")
    local unhappy = moodleLevel(moodles, "unhappy")
    if (boredom >= 2 or unhappy >= 2) and (t - lastBoredomAlertMs > 60000) then
        emit("boredom", "tedio")
        lastBoredomAlertMs = t
    end

    local sick = moodleLevel(moodles, "sick")
    if sick >= 1 and (t - lastSickAlertMs > 45000) then
        emit("sickness", "enjoo")
        lastSickAlertMs = t
    end
end

-- -------------------------------------------------------------
-- EVENTO 6: Pesadelo ao acordar
-- -------------------------------------------------------------
function TTSEvents.checkNightmare(player)
    local isAsleep = player:isAsleep()
    if wasAsleep and not isAsleep then
        local moodles = player:getMoodles()
        if moodles then
            if moodleTypes == nil then resolveMoodleTypes() end
            if moodleLevel(moodles, "panic") >= 1 then
                emit("nightmare", "pesadelo")
            end
        end
    end
    wasAsleep = isAsleep
end

-- -------------------------------------------------------------
-- EVENTO 7: Coleta de Loot Importante
-- -------------------------------------------------------------
local lootByName = {}

function TTSEvents.checkLooting(player)
    local inv = player:getInventory()
    if not inv then return end
    local items = inv:getItems()
    if not items then return end
    local currentCount = items:size()

    local previous = lastInventoryCount
    lastInventoryCount = currentCount
    if previous == nil or currentCount <= previous then return end

    local latestItem = items:get(currentCount - 1)
    if not latestItem then return end

    local category = latestItem:getCategory()
    local itemName = latestItem:getName()

    if category == "Weapon" or category == "Food" or category == "Literature" or category == "Drainable" then
        local t = nowMs()
        if t - lastLootAlertMs > 3000 and t - (lootByName[itemName] or -999999) > 60000 then
            lastLootAlertMs = t
            lootByName[itemName] = t
            emit("loot_rare", category .. ":" .. itemName)
        end
    end
end

-- -------------------------------------------------------------
-- EVENTO 8: Controlo de Abates (Combate)
-- -------------------------------------------------------------
function TTSEvents.checkCombatKills(player)
    local currentKills = player:getZombieKills()
    if lastZombieKills == nil then
        lastZombieKills = currentKills
        return
    end

    if currentKills > lastZombieKills then
        lastZombieKills = currentKills
        local t = nowMs()
        if t - lastCombatAlertMs < 3000 then return end
        lastCombatAlertMs = t
        emit("combat_clear", "limpou_area")
    end
end

-- -------------------------------------------------------------
-- EVENTO 9: Fuga Descoberta (Furtividade Quebrada)
-- -------------------------------------------------------------
function TTSEvents.checkStealthBroken(player)
    if not player:isSneaking() then return end
    local t = nowMs()
    if t - lastStealthAlertMs < 15000 then return end

    local zombieList = player:getCell():getZombieList()
    if not zombieList then return end
    local px, py = player:getX(), player:getY()

    for i = 0, zombieList:size() - 1 do
        local z = zombieList:get(i)
        if z and z:getTarget() == player then
            local dx = z:getX() - px
            local dy = z:getY() - py
            if (dx*dx + dy*dy) <= 25 then
                emit("stealth_broken", "descoberto")
                lastStealthAlertMs = t
                break
            end
        end
    end
end

-- -------------------------------------------------------------
-- EVENTO 10: Armas de Fogo
-- -------------------------------------------------------------
function TTSEvents.checkWeapons(player)
    local item = player:getPrimaryHandItem()
    if not item then return end
    
    if instanceof(item, "HandWeapon") and item:isRanged() then
        local t = nowMs()
        
        local jammed = callIfExists(item, "isJammed")
        if jammed and not wasJammed then
            if t - lastJammedAlertMs > 10000 then
                emit("weapon_jammed", "travou")
                lastJammedAlertMs = t
            end
        end
        wasJammed = jammed or false

        local ammoCount = callIfExists(item, "getCurrentAmmoCount")
        if ammoCount and ammoCount == 0 then
            if t - lastAmmoAlertMs > 15000 then
                emit("ammo_empty", "sem_municao")
                lastAmmoAlertMs = t
            end
        end
    end
end

-- -------------------------------------------------------------
-- EVENTO 11: Veículos
-- -------------------------------------------------------------
function TTSEvents.checkVehicle(player)
    local vehicle = player:getVehicle()
    if vehicle then
        wasInVehicle = true
        local engineRunning = vehicle:isEngineRunning()
        local t = nowMs()
        if not engineRunning and t - lastVehicleAlertMs > 30000 then
        end
    else
        if wasInVehicle then
            wasInVehicle = false
        end
    end
end

-- -------------------------------------------------------------
-- Loop Principal
-- -------------------------------------------------------------
local function onPlayerUpdate(player)
    if not player or not player:isLocalPlayer() then return end

    tickCounter = tickCounter + 1
    if tickCounter % 10 ~= 0 then return end

    safe("checkBehindZombie", TTSEvents.checkBehindZombie, player)
    safe("checkWounds", TTSEvents.checkWounds, player)
    safe("checkHealth", TTSEvents.checkHealth, player)
    safe("checkBleeding", TTSEvents.checkBleeding, player)
    safe("checkWeather", TTSEvents.checkWeather)
    safe("checkResting", TTSEvents.checkResting, player)
    safe("checkMoodles", TTSEvents.checkMoodles, player)
    safe("checkNightmare", TTSEvents.checkNightmare, player)
    safe("checkLooting", TTSEvents.checkLooting, player)
    safe("checkCombatKills", TTSEvents.checkCombatKills, player)
    safe("checkStealthBroken", TTSEvents.checkStealthBroken, player)
    safe("checkWeapons", TTSEvents.checkWeapons, player)
    safe("checkVehicle", TTSEvents.checkVehicle, player)
end

Events.OnPlayerUpdate.Add(onPlayerUpdate)

print("[TTS MOD] Mod de Eventos de Voz carregado com sucesso! (v16)")