package com.naveenhospital.medtrack.operations

import android.os.SystemClock
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import com.naveenhospital.medtrack.core.data.repository.StaffToolsRepository
import kotlinx.coroutines.delay

/** Static, compact banner. No ticker, external notification delivery or persisted content. */
@Composable
fun StaffSummaryBanner(repository: StaffToolsRepository, onOpen: (Int) -> Unit) {
    val session by repository.activeSession.collectAsState()
    val announcements by repository.announcements.collectAsState()
    val reminders by repository.dueReminderCount.collectAsState()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var elapsed by remember { mutableLongStateOf(SystemClock.elapsedRealtime()) }
    LaunchedEffect(session, lifecycle) {
        if (session != null) lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            while (true) {
                repository.refreshBanner()
                repository.refreshDueNotices()
                delay(60_000)
            }
        }
    }
    LaunchedEffect(session, lifecycle) {
        if (session != null) lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            while (true) {
                elapsed = SystemClock.elapsedRealtime()
                if (repository.announcements.value.size != repository.visibleAnnouncements().size) repository.refreshBanner()
                delay(1_000)
            }
        }
    }
    val visible = remember(announcements, elapsed, session) { repository.visibleAnnouncements() }
    if (session != null && (visible.isNotEmpty() || reminders > 0)) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            visible.maxByOrNull { when (it.priority) { "urgent" -> 2; "important" -> 1; else -> 0 } }?.let { row ->
                Card(onClick = { onOpen(2) }, modifier = Modifier.fillMaxWidth()) {
                    Text(row.title, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(10.dp))
                }
            }
            if (reminders > 0) TextButton(onClick = { onOpen(1) }) { Text("$reminders due reminders") }
        }
    }
}
