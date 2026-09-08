package com.naveenhospital.medtrack.feature.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import com.naveenhospital.medtrack.core.domain.model.UpcomingPage
import com.naveenhospital.medtrack.core.domain.model.UpcomingTask
import com.naveenhospital.medtrack.core.domain.model.groupUpcomingTasks
import com.naveenhospital.medtrack.core.domain.model.shiftUpcomingDate
import kotlinx.coroutines.CancellationException

@Composable
internal fun UpcomingScreen(
    filterKey: Any, refreshing: Boolean,
    load: suspend (String?, String?) -> UpcomingPage,
    onOpenCase: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val loader by rememberUpdatedState(load)
    var startDate by remember { mutableStateOf<String?>(null) }
    var requestVersion by remember { mutableStateOf(0) }
    var cursor by remember(filterKey, startDate, requestVersion) { mutableStateOf<String?>(null) }
    var page by remember(filterKey, startDate, requestVersion) { mutableStateOf<UpcomingPage?>(null) }
    var rows by remember(filterKey, startDate, requestVersion) { mutableStateOf<List<UpcomingTask>>(emptyList()) }
    var error by remember(filterKey, startDate, requestVersion) { mutableStateOf<String?>(null) }
    var loading by remember(filterKey, startDate, requestVersion) { mutableStateOf(true) }
    var expandedGroup by remember(filterKey, startDate) { mutableStateOf<String?>(null) }
    LaunchedEffect(filterKey, startDate, requestVersion, cursor, refreshing) {
        if (refreshing) {
            rows = emptyList()
            page = null
            cursor = null
            loading = true
            return@LaunchedEffect
        }
        loading = true
        error = null
        try {
            val response = loader(startDate, cursor)
            rows = ((if (cursor == null) emptyList() else rows) + response.results).distinctBy { it.id }
            page = response
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (failure: Exception) {
            error = failure.message ?: "Unable to load upcoming tasks"
        } finally {
            loading = false
        }
    }
    val groups = remember(rows) { groupUpcomingTasks(rows) }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        page?.let { current ->
            Text("${current.startDate} – ${current.endDate}", color = MedtrackColors.Ink, fontWeight = FontWeight.Bold)
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            TextButton(enabled = page?.let { it.startDate > it.hospitalToday } == true && !loading, onClick = {
                page?.let { current -> startDate = shiftUpcomingDate(current.startDate, -7)?.coerceAtLeast(current.hospitalToday) }
            }) { Text("Previous") }
            TextButton(enabled = !loading, onClick = { startDate = null; requestVersion += 1 }) { Text("Next 7 days") }
            TextButton(enabled = page != null && !loading, onClick = { startDate = shiftUpcomingDate(page!!.startDate, 7) }) { Text("Later") }
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(bottom = 96.dp)) {
            groups.groupBy { it.dueDate }.forEach { (date, datedGroups) ->
                item(key = "date:$date") {
                    Text(date, color = MedtrackColors.Primary, style = MaterialTheme.typography.titleSmall)
                }
                items(datedGroups, key = { it.key }) { group ->
                    val first = group.tasks.first()
                    Surface(color = MedtrackColors.Card, shape = MaterialTheme.shapes.medium, border = BorderStroke(1.dp, MedtrackColors.Border)) {
                        Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                            Text(first.patientName, fontWeight = FontWeight.Bold, color = MedtrackColors.Ink)
                            Text(first.department, color = MedtrackColors.Muted, style = MaterialTheme.typography.labelMedium)
                            if (group.tasks.size == 1 || expandedGroup == group.key) {
                                group.tasks.forEach { task ->
                                    Text(task.title, color = MedtrackColors.Ink)
                                    Text(task.assignedUserName.ifBlank { "Unassigned" }, style = MaterialTheme.typography.bodySmall, color = MedtrackColors.Muted)
                                }
                            }
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                if (group.tasks.size > 1) {
                                    TextButton(onClick = { expandedGroup = if (expandedGroup == group.key) null else group.key }) {
                                        Text(if (expandedGroup == group.key) "Hide ${group.tasks.size} tasks" else "Show ${group.tasks.size} tasks")
                                    }
                                }
                                TextButton(onClick = { onOpenCase(group.caseId.toString()) }) { Text("Open case") }
                            }
                        }
                    }
                }
            }
            item {
                if (loading) Text("Loading tasks…", color = MedtrackColors.Muted)
                else if (error != null) {
                    Text(error.orEmpty(), color = MedtrackColors.Danger)
                    TextButton(onClick = { requestVersion += 1 }) { Text("Retry") }
                } else if (rows.isEmpty()) Text("No scheduled tasks in these dates", color = MedtrackColors.Muted)
                else {
                    Text("${rows.size} tasks loaded", color = MedtrackColors.Muted, style = MaterialTheme.typography.labelSmall)
                    if (page?.nextCursor != null) TextButton(onClick = { cursor = page?.nextCursor }) { Text("Load more tasks") }
                }
            }
        }
    }
}
