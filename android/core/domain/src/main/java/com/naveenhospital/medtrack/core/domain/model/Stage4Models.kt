package com.naveenhospital.medtrack.core.domain.model

data class UpcomingTask(
    val id: Long, val caseId: Long, val patientName: String, val department: String,
    val title: String, val dueDate: String, val assignedUserName: String,
)
data class UpcomingPage(
    val hospitalToday: String, val startDate: String, val endDate: String,
    val timezone: String, val results: List<UpcomingTask>, val nextCursor: String?,
)
data class CaseTimelineEvent(
    val id: String, val eventType: String, val eventLabel: String, val timestamp: String,
    val actor: String, val taskTitle: String, val headline: String, val reason: String, val details: String,
)
data class CaseTimelinePage(
    val results: List<CaseTimelineEvent>, val nextCursor: String?, val timezone: String,
)

data class UpcomingGroup(val dueDate: String, val caseId: Long, val tasks: List<UpcomingTask>) {
    val key: String get() = "$dueDate:$caseId"
}
fun groupUpcomingTasks(tasks: List<UpcomingTask>): List<UpcomingGroup> = tasks.distinctBy { it.id }
    .sortedWith(compareBy<UpcomingTask> { it.dueDate }.thenBy { it.caseId }.thenBy { it.id })
    .groupBy { it.dueDate to it.caseId }
    .map { (key, rows) -> UpcomingGroup(key.first, key.second, rows) }

/** Calendar DATE arithmetic, independent of the handset timezone and DST. */
fun shiftUpcomingDate(value: String, days: Int): String? {
    if (!Regex("\\d{4}-\\d{2}-\\d{2}").matches(value)) return null
    val format = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US).apply {
        isLenient = false
        timeZone = java.util.TimeZone.getTimeZone("UTC")
    }
    val date = runCatching { format.parse(value) }.getOrNull() ?: return null
    val calendar = java.util.Calendar.getInstance(format.timeZone).apply {
        time = date
        add(java.util.Calendar.DAY_OF_MONTH, days)
    }
    return format.format(calendar.time)
}

data class RelatedCase(val id: Long, val department: String, val diagnosis: String, val status: String)
data class RelatedCasePage(val results: List<RelatedCase>, val nextCursor: String?)
