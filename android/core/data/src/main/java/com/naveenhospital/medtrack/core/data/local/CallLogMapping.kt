package com.naveenhospital.medtrack.core.data.local

import com.naveenhospital.medtrack.core.domain.model.PatientCallLog
import com.naveenhospital.medtrack.core.network.model.CallLogDto
import java.time.OffsetDateTime

internal fun CallLogDto.toEntity(ownerAccountId: String, caseId: String) = CallLogEntity(
    ownerAccountId = ownerAccountId, id = id, caseId = caseId, taskId = taskId,
    taskTitle = taskTitle, reason = reason, outcome = outcome,
    outcomeLabel = outcomeLabel ?: outcome, notes = notes.orEmpty(), staffUser = staffUser,
    createdAt = createdAt, createdAtEpochMicros = OffsetDateTime.parse(createdAt).toInstant().let { it.epochSecond * 1_000_000 + it.nano / 1_000 },
    clientEventAt = clientEventAt,
)

internal fun CallLogEntity.toDomain() = PatientCallLog(
    id = id, taskId = taskId, taskTitle = taskTitle, reason = reason,
    outcomeLabel = outcomeLabel, notes = notes, staffUser = staffUser,
    createdAt = createdAt, clientEventAt = clientEventAt,
)
