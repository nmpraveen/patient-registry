package com.naveenhospital.medtrack.feature.cases

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.domain.model.CaseTimelineEvent
import com.naveenhospital.medtrack.core.domain.model.CaseTimelinePage
import kotlinx.coroutines.CancellationException
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

internal data class TimelineUiState(
    val events: List<CaseTimelineEvent>, val timezone: String,
    val loading: Boolean, val error: String?, val hasMore: Boolean,
    val loadMore: () -> Unit, val retry: () -> Unit,
)

@Composable
internal fun rememberTimeline(
    caseId: String, filter: String, refreshing: Boolean,
    load: suspend (String, String?) -> CaseTimelinePage,
): TimelineUiState {
    val loader by rememberUpdatedState(load)
    var events by remember(caseId, filter) { mutableStateOf<List<CaseTimelineEvent>>(emptyList()) }
    var timezone by remember(caseId, filter) { mutableStateOf("UTC") }
    var nextCursor by remember(caseId, filter) { mutableStateOf<String?>(null) }
    var requestedCursor by remember(caseId, filter) { mutableStateOf<String?>(null) }
    var retryCount by remember(caseId, filter) { mutableStateOf(0) }
    var loading by remember(caseId, filter) { mutableStateOf(true) }
    var error by remember(caseId, filter) { mutableStateOf<String?>(null) }
    LaunchedEffect(caseId, filter, refreshing, requestedCursor, retryCount) {
        if (refreshing) {
            events = emptyList()
            nextCursor = null
            requestedCursor = null
            loading = true
            return@LaunchedEffect
        }
        loading = true
        error = null
        try {
            val page = loader(filter, requestedCursor)
            events = ((if (requestedCursor == null) emptyList() else events) + page.results).distinctBy { it.id }
            nextCursor = page.nextCursor
            timezone = page.timezone
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (failure: Exception) {
            error = failure.message ?: "Unable to load timeline"
        } finally {
            loading = false
        }
    }
    return TimelineUiState(events, timezone, loading, error, nextCursor != null,
        loadMore = { if (!loading) requestedCursor = nextCursor },
        retry = { retryCount += 1 },
    )
}

/** Server order stays authoritative; timestamps are formatted only for display. */
internal fun timelineTimestamp(value: String, timezone: String): String {
    val normalized = value.replace(Regex("""(\.\d{3})\d+"""), "$1")
    val parsed = listOf("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", "yyyy-MM-dd'T'HH:mm:ssXXX")
        .firstNotNullOfOrNull { pattern ->
            runCatching { SimpleDateFormat(pattern, Locale.US).apply { isLenient = false }.parse(normalized) }.getOrNull()
        } ?: return value
    return SimpleDateFormat("dd MMM yyyy, HH:mm z", Locale.getDefault()).apply {
        timeZone = TimeZone.getTimeZone(timezone)
    }.format(parsed)
}

@Composable
internal fun TimelineEventRow(event: CaseTimelineEvent, timezone: String) {
    Column(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(event.eventLabel, style = MaterialTheme.typography.labelMedium, color = MedtrackColors.Primary)
        Text(event.headline, fontWeight = FontWeight.Bold, color = MedtrackColors.Ink)
        if (event.taskTitle.isNotBlank() && event.taskTitle != event.headline) Text(event.taskTitle, color = MedtrackColors.Muted)
        if (event.reason.isNotBlank()) Text(event.reason, color = MedtrackColors.Ink)
        if (event.details.isNotBlank()) Text(event.details, color = MedtrackColors.InkSoft)
        Text(listOf(timelineTimestamp(event.timestamp, timezone), event.actor).filter { it.isNotBlank() }.joinToString(" · "),
            style = MaterialTheme.typography.labelSmall, color = MedtrackColors.Muted)
    }
}
