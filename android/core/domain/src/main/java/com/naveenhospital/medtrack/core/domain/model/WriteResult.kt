package com.naveenhospital.medtrack.core.domain.model

data class WriteResult(
    val clientWriteId: String,
    val queued: Boolean,
    val message: String,
    val conflict: Boolean = false,
)

data class SyncConflict(
    val clientWriteId: String,
    val writeType: String,
    val caseId: String?,
    val taskId: String?,
    val message: String,
    val createdAtMillis: Long,
)
