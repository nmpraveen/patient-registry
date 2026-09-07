package com.naveenhospital.medtrack.core.data.local

import com.naveenhospital.medtrack.core.domain.model.PatientCallLog
import com.naveenhospital.medtrack.core.network.model.CallLogDto
import java.util.Date
import java.util.GregorianCalendar
import java.util.Locale
import java.util.TimeZone

internal fun CallLogDto.toEntity(ownerAccountId: String, caseId: String) = CallLogEntity(
    ownerAccountId = ownerAccountId, id = id, caseId = caseId, taskId = taskId,
    taskTitle = taskTitle, reason = reason, outcome = outcome,
    outcomeLabel = outcomeLabel ?: outcome, notes = notes.orEmpty(), staffUser = staffUser,
    createdAt = createdAt, createdAtEpochMicros = receiptEpochMicros(createdAt),
    clientEventAt = clientEventAt,
)

private val receiptTimestamp = Regex(
    """(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})""",
)

/** Parse server ISO timestamps without API 26 java.time or losing submillisecond order. */
internal fun receiptEpochMicros(value: String): Long {
    val parts = requireNotNull(receiptTimestamp.matchEntire(value)) { "Invalid call receipt timestamp." }.groupValues
    val year = parts[1].toInt()
    require(year > 0) { "Invalid call receipt year." }
    val calendar = GregorianCalendar(TimeZone.getTimeZone("UTC"), Locale.ROOT).apply {
        gregorianChange = Date(Long.MIN_VALUE)
        isLenient = false
        clear()
        set(year, parts[2].toInt() - 1, parts[3].toInt(), parts[4].toInt(), parts[5].toInt(), parts[6].toInt())
    }
    val offset = parts[8]
    val offsetMinutes = if (offset == "Z") 0 else {
        val hours = offset.substring(1, 3).toInt()
        val minutes = offset.substring(4, 6).toInt()
        require(hours <= 18 && minutes <= 59 && (hours < 18 || minutes == 0)) { "Invalid call receipt offset." }
        (hours * 60 + minutes) * if (offset[0] == '-') -1 else 1
    }
    val fractionMicros = parts[7].padEnd(6, '0').take(6).toLong()
    return calendar.timeInMillis * 1_000 - offsetMinutes * 60_000_000L + fractionMicros
}

internal fun CallLogEntity.toDomain() = PatientCallLog(
    id = id, taskId = taskId, taskTitle = taskTitle, reason = reason,
    outcomeLabel = outcomeLabel, notes = notes, staffUser = staffUser,
    createdAt = createdAt, createdAtEpochMicros = createdAtEpochMicros, clientEventAt = clientEventAt,
)
