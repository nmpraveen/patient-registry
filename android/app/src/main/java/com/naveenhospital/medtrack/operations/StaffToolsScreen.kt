package com.naveenhospital.medtrack.operations

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.SystemClock
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import com.naveenhospital.medtrack.core.data.repository.*
import com.naveenhospital.medtrack.core.designsystem.MedtrackPullRefreshBox
import com.naveenhospital.medtrack.core.domain.model.*
import com.naveenhospital.medtrack.core.network.model.ReminderOccurrenceDto
import com.naveenhospital.medtrack.core.network.model.StaffReminderDto
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable
fun StaffToolsScreen(repository: StaffToolsRepository, onBack: () -> Unit, initialTab: Int = 0) {
    val session by repository.activeSession.collectAsState()
    key(session) {
        if (session == null) {
            TextButton(onClick = onBack) { Text("Back") }
        } else {
            StaffToolsContent(repository, onBack, initialTab)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun StaffToolsContent(repository: StaffToolsRepository, onBack: () -> Unit, initialTab: Int) {
    val state by repository.screen.collectAsState()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val listState = rememberLazyListState()
    var tab by remember { mutableIntStateOf(initialTab.coerceIn(0, 2)) }
    var query by remember { mutableStateOf("") }
    var favourites by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("notices") }
    var page by remember { mutableIntStateOf(1) }
    var selected by remember { mutableStateOf<Long?>(null) }
    var assignment by remember { mutableStateOf<StaffReminderDto?>(null) }
    var refresh by remember { mutableIntStateOf(0) }
    var elapsed by remember { mutableLongStateOf(SystemClock.elapsedRealtime()) }
    var dialError by remember { mutableStateOf<String?>(null) }

    fun back() {
        repository.clearScreen()
        if (assignment != null) { assignment = null; query = ""; page = 1 }
        else if (selected != null) { selected = null; page = 1 }
        else onBack()
    }
    BackHandler { back() }
    DisposableEffect(repository) { onDispose { repository.clearScreen() } }
    LaunchedEffect(tab, selected, page, query, favourites, status, assignment) { listState.scrollToItem(0) }
    LaunchedEffect(tab, query, favourites, status, page, selected, assignment, refresh) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            // Debounce search and cancel obsolete requests when the query or route changes.
            if (query.isNotBlank()) delay(250)
            while (true) {
                val id = selected
                val definition = assignment
                when {
                    definition != null -> repository.assignees(definition, query, page)
                    tab == 0 && id != null -> repository.contact(id)
                    tab == 0 -> repository.directory(query, favourites, page)
                    tab == 1 && id != null -> repository.reminder(id, page)
                    tab == 1 -> repository.reminders(status, page)
                    id != null -> repository.announcement(id)
                    else -> repository.announcementList(page)
                }
                delay(60_000)
            }
        }
    }
    LaunchedEffect(lifecycle) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            while (true) {
                elapsed = SystemClock.elapsedRealtime()
                when (val current = repository.screen.value.content) {
                    is StaffContent.Announcements -> if (current.rows.any { current.clock?.isVisible(it, elapsed) != true }) refresh++
                    is StaffContent.Announcement -> if (!current.clock.isVisible(current.row, elapsed)) refresh++
                    else -> Unit
                }
                delay(1_000)
            }
        }
    }

    Column(Modifier.fillMaxSize().padding(horizontal = 12.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            TextButton(onClick = { back() }) { Text("Back") }
            TextButton(onClick = { assignment = null; refresh++ }, enabled = !state.loading) { Text("Refresh") }
        }
        Text("Staff tools", style = MaterialTheme.typography.headlineSmall)
        ScrollableTabRow(selectedTabIndex = tab, edgePadding = 0.dp) {
            listOf("PhoneBook", "Reminders", "Announcements").forEachIndexed { index, title ->
                Tab(selected = tab == index, onClick = {
                    repository.clearScreen()
                    tab = index; page = 1; selected = null; assignment = null; query = ""; dialError = null
                }, text = { Text(title) })
            }
        }
        if ((tab == 0 && selected == null) || assignment != null) {
            OutlinedTextField(value = query, onValueChange = { query = it.take(100); page = 1 },
                label = { Text(if (assignment == null) "Search contacts" else "Search staff") },
                singleLine = true, modifier = Modifier.fillMaxWidth())
        }
        if (tab == 0 && selected == null) {
            FilterChip(selected = favourites, onClick = { favourites = !favourites; page = 1 }, label = { Text("Favourites") })
        }
        if (tab == 1 && selected == null) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("notices" to "Due", "pending" to "Pending", "completed" to "History").forEach { (value, title) ->
                    FilterChip(selected = status == value, onClick = { status = value; page = 1 }, label = { Text(title) })
                }
            }
        }
        if (state.loading) LinearProgressIndicator(Modifier.fillMaxWidth())
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(vertical = 8.dp)) }
        dialError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        val content = state.content
        MedtrackPullRefreshBox(
            modifier = Modifier.weight(1f),
            isRefreshing = state.loading,
            onRefresh = { assignment = null; refresh++ },
            canRefresh = { listState.firstVisibleItemIndex == 0 && listState.firstVisibleItemScrollOffset == 0 },
        ) {
        LazyColumn(Modifier.fillMaxSize(), state = listState, verticalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(vertical = 12.dp)) {
            when (content) {
                is StaffContent.Directory -> {
                    if (content.rows.isEmpty()) item { Text("No contacts") }
                    items(content.rows, key = { it.id }) { row ->
                        StaffRow(row.name, listOf(row.role, row.organisation).filter(String::isNotBlank).joinToString(" · "), onClick = { selected = row.id; page = 1 })
                    }
                }
                is StaffContent.Contact -> {
                    val row = content.row
                    item { Text(row.name, style = MaterialTheme.typography.titleLarge) }
                    item { Text(listOf(row.role, row.organisation).filter(String::isNotBlank).joinToString(" · ")) }
                    item { TextButton(onClick = { scope.launch { repository.favourite(row.id, !row.favourite) } }) {
                        Text(if (row.favourite) "Remove favourite" else "Add favourite")
                    } }
                    items(row.phones) { phone ->
                        Column {
                            Text(listOf(phone.label, phone.number).filter(String::isNotBlank).joinToString(" · "))
                            if (phone.extension.isNotBlank()) Text("Extension ${phone.extension}")
                            TextButton(enabled = phone.dialNumber() != null, onClick = {
                                phone.dialNumber()?.let { number ->
                                    try {
                                        context.startActivity(Intent(Intent.ACTION_DIAL, Uri.fromParts("tel", number, null)))
                                        dialError = null
                                    } catch (_: ActivityNotFoundException) { dialError = "No dialer available." }
                                    catch (_: SecurityException) { dialError = "Unable to open the dialer." }
                                }
                            }) { Text("Dial ${phone.label.ifBlank { "number" }}") }
                        }
                    }
                    if (row.notes.isNotBlank()) item { Text(row.notes) }
                }
                is StaffContent.Reminders -> {
                    if (content.rows.isEmpty()) item { Text(if (status == "notices") "No due reminders" else "No reminders") }
                    items(content.rows, key = { it.id }) { row ->
                        StaffRow(row.title, "${row.dueDate} · ${row.assigneeName}" + if (row.completedAt != null) " · Completed" else "",
                            onClick = { selected = row.reminderId; page = 1 })
                    }
                }
                is StaffContent.Reminder -> {
                    val definition = content.definition
                    item {
                        Text(definition.title, style = MaterialTheme.typography.titleLarge)
                        Text("${definition.assigneeName}${if (!definition.assigneeActive) " · Inactive staff" else ""}")
                        Text("${recurrenceLabel(definition.recurrence)} · Anchor ${definition.dueDate}")
                        Text("Notice ${definition.advanceNoticeDays} days before")
                        if (!definition.isActive) Text("Inactive reminder")
                        if (definition.canAssign) TextButton(onClick = { assignment = definition; query = ""; page = 1 }) { Text("Assign") }
                        Text("Occurrences and history", style = MaterialTheme.typography.titleMedium)
                    }
                    items(content.history, key = { it.id }) { row ->
                        ReminderHistoryRow(row, onComplete = { scope.launch { repository.complete(row, page) } })
                    }
                }
                is StaffContent.Assignees -> {
                    item { Text("Assign ${content.definition.title}", style = MaterialTheme.typography.titleMedium) }
                    if (content.rows.isEmpty()) item { Text("No matching staff") }
                    items(content.rows, key = { it.id }) { row ->
                        StaffRow(row.name, "", onClick = {
                            scope.launch {
                                repository.assign(content.definition, row.id)
                                if (repository.screen.value.content is StaffContent.Reminder) { assignment = null; query = ""; page = 1 }
                            }
                        })
                    }
                }
                is StaffContent.Announcements -> {
                    val visible = content.rows.filter { content.clock?.isVisible(it, elapsed) == true }
                    if (visible.isEmpty()) item { Text("No announcements") }
                    items(visible, key = { it.id }) { row ->
                        StaffRow(row.title, "${row.priority} · ${row.publisher}", onClick = { selected = row.id; page = 1 })
                    }
                }
                is StaffContent.Announcement -> {
                    if (content.clock.isVisible(content.row, elapsed)) item {
                        Text(content.row.priority.replaceFirstChar(Char::uppercaseChar), style = MaterialTheme.typography.titleMedium)
                        Text(content.row.text)
                        Text(content.row.publisher, style = MaterialTheme.typography.labelMedium)
                    } else item { Text("Announcement expired") }
                }
                null -> Unit
            }
        }
        }
        val hasNext = when (content) {
            is StaffContent.Directory -> content.hasNext
            is StaffContent.Reminders -> content.hasNext
            is StaffContent.Reminder -> content.hasNext
            is StaffContent.Assignees -> content.hasNext
            is StaffContent.Announcements -> content.hasNext
            else -> false
        }
        if (page > 1 || hasNext) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            TextButton(enabled = page > 1 && !state.loading, onClick = { page-- }) { Text("Previous") }
            Text("Page $page", modifier = Modifier.padding(top = 12.dp))
            TextButton(enabled = hasNext && !state.loading, onClick = { page++ }) { Text("Next") }
        }
    }
}

@Composable
private fun StaffRow(title: String, subtitle: String, onClick: () -> Unit) {
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            if (subtitle.isNotBlank()) Text(subtitle, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun ReminderHistoryRow(row: ReminderOccurrenceDto, onComplete: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text(row.dueDate, style = MaterialTheme.typography.titleMedium)
            row.completedAt?.let { Text("Completed $it · Staff ${row.completedById ?: "—"}") }
                ?: Text(if (row.isActive) "Pending" else "Inactive")
            if (row.canComplete && row.completedAt == null) TextButton(onClick = onComplete) { Text("Complete") }
        }
    }
}

private fun recurrenceLabel(value: String): String = when (value) {
    "ONCE" -> "Once"
    "MONTHLY" -> "Monthly"
    "EVERY_TWO_MONTHS" -> "Every two months"
    "YEARLY" -> "Yearly"
    else -> value
}
