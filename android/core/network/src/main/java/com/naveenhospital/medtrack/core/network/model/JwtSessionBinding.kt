package com.naveenhospital.medtrack.core.network.model

import java.nio.charset.StandardCharsets
import java.util.UUID

data class JwtSessionBinding(
    val accountId: String,
    val mobileDeviceId: String?,
)

class MalformedJwtSessionException(message: String) : IllegalArgumentException(message)

fun AuthSessionDto.requireSessionBinding(
    expectedAccountId: String? = null,
    expectedMobileDeviceId: String? = null,
): JwtSessionBinding {
    val refreshToken = refresh?.takeIf { it.isNotBlank() }
        ?: throw MalformedJwtSessionException("Authentication returned no rotated refresh token.")
    val accessClaims = access.jwtSecurityClaims("access")
    val refreshClaims = refreshToken.jwtSecurityClaims("refresh")
    if (accessClaims.accountId != refreshClaims.accountId) {
        throw MalformedJwtSessionException("Access and refresh tokens belong to different accounts.")
    }
    if (accessClaims.mobileDeviceId != refreshClaims.mobileDeviceId) {
        throw MalformedJwtSessionException("Access and refresh tokens have different mobile-device bindings.")
    }
    if (expectedAccountId != null && accessClaims.accountId != expectedAccountId) {
        throw MalformedJwtSessionException("Authentication tokens do not belong to the expected account.")
    }
    if (accessClaims.mobileDeviceId != expectedMobileDeviceId) {
        throw MalformedJwtSessionException("Authentication tokens are not bound to the approved mobile device.")
    }
    return accessClaims
}

private fun String.jwtSecurityClaims(tokenType: String): JwtSessionBinding {
    val segments = split('.')
    if (segments.size != 3 || segments.any { it.isBlank() }) {
        throw MalformedJwtSessionException("Authentication returned a malformed $tokenType token.")
    }
    val payload = try {
        String(decodeBase64Url(segments[1]), StandardCharsets.UTF_8)
    } catch (failure: IllegalArgumentException) {
        throw MalformedJwtSessionException("Authentication returned a malformed $tokenType token.")
    }
    val accountMatches = USER_ID.findAll(payload).toList()
    if (accountMatches.size != 1) {
        throw MalformedJwtSessionException("Authentication token has no unambiguous account binding.")
    }
    val accountId = accountMatches.single().groupValues.drop(1).firstOrNull { it.isNotBlank() }
        ?: throw MalformedJwtSessionException("Authentication token has no account binding.")
    val deviceKeyPresent = MOBILE_DEVICE_KEY.containsMatchIn(payload)
    val deviceMatches = MOBILE_DEVICE_ID.findAll(payload).toList()
    if (deviceMatches.size > 1 || (deviceKeyPresent && deviceMatches.size != 1)) {
        throw MalformedJwtSessionException("Authentication token has a malformed mobile-device binding.")
    }
    val mobileDeviceId = deviceMatches.singleOrNull()?.groupValues?.get(1)?.let { raw ->
        try {
            UUID.fromString(raw).toString()
        } catch (failure: IllegalArgumentException) {
            throw MalformedJwtSessionException("Authentication token has a malformed mobile-device identifier.")
        }
    }
    return JwtSessionBinding(accountId = accountId, mobileDeviceId = mobileDeviceId)
}

private fun decodeBase64Url(input: String): ByteArray {
    val output = ByteArray((input.length * 6) / 8)
    var buffer = 0
    var bufferedBits = 0
    var outputIndex = 0
    input.forEach { character ->
        val value = when (character) {
            in 'A'..'Z' -> character.code - 'A'.code
            in 'a'..'z' -> character.code - 'a'.code + 26
            in '0'..'9' -> character.code - '0'.code + 52
            '-' -> 62
            '_' -> 63
            else -> throw IllegalArgumentException("Invalid base64url character.")
        }
        buffer = (buffer shl 6) or value
        bufferedBits += 6
        if (bufferedBits >= 8) {
            bufferedBits -= 8
            output[outputIndex++] = (buffer shr bufferedBits).toByte()
            buffer = if (bufferedBits == 0) 0 else buffer and ((1 shl bufferedBits) - 1)
        }
    }
    if (bufferedBits >= 6 || buffer != 0) {
        throw IllegalArgumentException("Invalid base64url padding.")
    }
    return output.copyOf(outputIndex)
}

private val USER_ID = Regex("""\"user_id\"\s*:\s*(?:\"([A-Za-z0-9._-]+)\"|([0-9]+))""")
private val MOBILE_DEVICE_KEY = Regex("""\"mobile_device_id\"\s*:""")
private val MOBILE_DEVICE_ID = Regex("""\"mobile_device_id\"\s*:\s*\"([0-9A-Fa-f-]+)\"""")
