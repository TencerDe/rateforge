SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]

local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local request_id = ARGV[4]

local window_start = now - window

redis.call(
    "ZREMRANGEBYSCORE",
    key,
    0,
    window_start
)

local count = redis.call(
    "ZCARD",
    key
)

if count >= limit then
    local oldest = redis.call(
        "ZRANGE",
        key,
        0,
        0,
        "WITHSCORES"
    )

    local retry_after = 0

    if oldest[2] then
        retry_after = tonumber(oldest[2]) + window - now
    end

    return {
        0,
        count,
        retry_after
    }
end

redis.call(
    "ZADD",
    key,
    now,
    request_id
)

redis.call(
    "EXPIRE",
    key,
    window
)

return {
    1,
    count + 1,
    0
}
"""