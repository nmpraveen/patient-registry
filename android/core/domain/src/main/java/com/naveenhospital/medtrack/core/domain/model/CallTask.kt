package com.naveenhospital.medtrack.core.domain.model

data class CallTask(
    val id: String,
    val caseId: String,
    val patientName: String,
    val phoneNumber: String,
    val dueDate: String,
    val reason: String,
    val latestOutcome: String?,
)
