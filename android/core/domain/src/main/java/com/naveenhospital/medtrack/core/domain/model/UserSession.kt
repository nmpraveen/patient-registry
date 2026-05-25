package com.naveenhospital.medtrack.core.domain.model

data class UserSession(
    val userId: String,
    val username: String,
    val displayName: String,
    val role: StaffRole,
    val accessToken: String,
    val refreshToken: String,
    val requiresDeviceUnlock: Boolean,
)
