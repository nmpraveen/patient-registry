package com.naveenhospital.medtrack.core.data.auth

import com.naveenhospital.medtrack.core.network.api.MedtrackApi
import com.naveenhospital.medtrack.core.network.model.LoginRequestDto
import com.naveenhospital.medtrack.core.network.model.RefreshTokenRequestDto
import com.naveenhospital.medtrack.core.network.model.UserProfileDto

class AuthRepository(
    private val api: MedtrackApi,
    private val tokenStore: TokenStore,
) {
    fun hasRefreshToken(): Boolean = tokenStore.hasRefreshToken()

    suspend fun login(username: String, password: String): UserProfileDto {
        val session = api.login(LoginRequestDto(username = username, password = password))
        tokenStore.saveSession(access = session.access, refresh = session.refresh)
        return api.me()
    }

    suspend fun currentUser(): UserProfileDto = api.me()

    suspend fun restoreSession(): Boolean {
        val refresh = tokenStore.refreshToken() ?: return false
        return runCatching {
            val session = api.refresh(RefreshTokenRequestDto(refresh = refresh))
            tokenStore.saveSession(access = session.access, refresh = session.refresh)
            true
        }.getOrElse {
            tokenStore.clear()
            false
        }
    }

    suspend fun logout(deviceToken: String? = null) {
        val refresh = tokenStore.refreshToken()
        if (!refresh.isNullOrBlank()) {
            runCatching {
                api.logout(
                    RefreshTokenRequestDto(
                        refresh = refresh,
                        deviceToken = deviceToken?.takeIf { it.isNotBlank() },
                    ),
                )
            }
        }
        tokenStore.clear()
    }
}
