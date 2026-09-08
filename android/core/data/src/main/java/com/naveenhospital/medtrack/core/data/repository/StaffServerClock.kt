package com.naveenhospital.medtrack.core.data.repository

import com.naveenhospital.medtrack.core.domain.model.StaffAnnouncement
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

/** Server time plus monotonic request elapsed time, conservatively including network latency. */
data class StaffServerClock(val serverMillis: Long, val receivedAt: Long) {
    fun isVisible(row: StaffAnnouncement, elapsed: Long): Boolean {
        val start = parseStaffTimestamp(row.startsAt) ?: return false
        val end = parseStaffTimestamp(row.endsAt) ?: return false
        val now = serverMillis + (elapsed - receivedAt).coerceAtLeast(0)
        return start <= now && now < end
    }

    companion object {
        fun from(timestamp: String?, elapsed: Long): StaffServerClock? =
            timestamp?.let(::parseStaffTimestamp)?.let { StaffServerClock(it, elapsed) }
    }
}

/** API 24 compatible, strict ISO timestamp parser; fractional seconds beyond millis truncate. */
internal fun parseStaffTimestamp(value: String): Long? {
    val match = Regex("^(\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2})(?:\\.(\\d{1,6}))?(Z|[+-]\\d{2}:\\d{2})$")
        .matchEntire(value) ?: return null
    val fraction = match.groupValues[2].padEnd(3, '0').take(3)
    val offset = match.groupValues[3].let { if (it == "Z") "+0000" else it.replace(":", "") }
    return runCatching {
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSZ", Locale.ROOT).apply {
            isLenient = false
            timeZone = TimeZone.getTimeZone("UTC")
        }.parse("${match.groupValues[1]}.$fraction$offset")?.time
    }.getOrNull()
}
