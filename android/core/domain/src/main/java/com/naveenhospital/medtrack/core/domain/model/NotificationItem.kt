package com.naveenhospital.medtrack.core.domain.model

data class NotificationItem(
    val id: String,
    val type: String,
    val title: String,
    val body: String,
    val caseId: String?,
    val taskId: String?,
    val createdAt: String,
    val isRead: Boolean,
)
