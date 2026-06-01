package com.naveenhospital.medtrack.core.designsystem

import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone

fun medtrackShortDateLabel(raw: String?): String? {
    val parsed = raw.parseMedtrackDate() ?: return raw?.trim()?.takeIf { it.isNotBlank() }
    val now = Calendar.getInstance()
    val then = Calendar.getInstance().apply { time = parsed.date }
    val dayDelta = then.dayNumber() - now.dayNumber()
    return when (dayDelta) {
        0 -> if (parsed.hasTime) "Today · ${timeFormatter().format(parsed.date)}" else "Today"
        1 -> if (parsed.hasTime) "Tomorrow · ${timeFormatter().format(parsed.date)}" else "Tomorrow"
        -1 -> if (parsed.hasTime) "Yesterday · ${timeFormatter().format(parsed.date)}" else "Yesterday"
        else -> {
            val sameYear = then.get(Calendar.YEAR) == now.get(Calendar.YEAR)
            val formatter = SimpleDateFormat(if (sameYear) "MMM d" else "MMM d, yyyy", Locale.getDefault())
            formatter.format(parsed.date)
        }
    }
}

fun medtrackTimestampLabel(raw: String?): String? {
    val parsed = raw.parseMedtrackDate() ?: return raw?.trim()?.takeIf { it.isNotBlank() }
    val dateLabel = medtrackShortDateLabel(raw).orEmpty()
    return if (parsed.hasTime && !dateLabel.contains(":")) {
        "$dateLabel · ${timeFormatter().format(parsed.date)}"
    } else {
        dateLabel
    }
}

private data class ParsedMedtrackDate(
    val date: Date,
    val hasTime: Boolean,
)

private fun String?.parseMedtrackDate(): ParsedMedtrackDate? {
    val value = this?.trim()?.takeIf { it.isNotBlank() }?.trimIsoFraction() ?: return null
    val patterns = listOf(
        DatePattern("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", true),
        DatePattern("yyyy-MM-dd'T'HH:mm:ssXXX", true),
        DatePattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", true, true),
        DatePattern("yyyy-MM-dd'T'HH:mm:ss'Z'", true, true),
        DatePattern("yyyy-MM-dd HH:mm:ss", true),
        DatePattern("yyyy-MM-dd", false),
    )
    return patterns.firstNotNullOfOrNull { pattern ->
        runCatching {
            val formatter = SimpleDateFormat(pattern.value, Locale.US).apply {
                isLenient = false
                if (pattern.utc) timeZone = TimeZone.getTimeZone("UTC")
            }
            formatter.parse(value)?.let { ParsedMedtrackDate(it, pattern.hasTime) }
        }.getOrNull()
    }
}

private fun String.trimIsoFraction(): String =
    replace(Regex("""(\.\d{3})\d+"""), "$1")

private data class DatePattern(
    val value: String,
    val hasTime: Boolean,
    val utc: Boolean = false,
)

private fun Calendar.dayNumber(): Int =
    get(Calendar.YEAR) * 366 + get(Calendar.DAY_OF_YEAR)

private fun timeFormatter(): SimpleDateFormat =
    SimpleDateFormat("h:mm a", Locale.getDefault())
