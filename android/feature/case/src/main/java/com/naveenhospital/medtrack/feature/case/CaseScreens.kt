package com.naveenhospital.medtrack.feature.cases

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Chat
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.OpenInNew
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.CloudDone
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.Favorite
import androidx.compose.material.icons.outlined.Flag
import androidx.compose.material.icons.outlined.Phone
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Tune
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.naveenhospital.medtrack.core.designsystem.MedtrackCard
import com.naveenhospital.medtrack.core.designsystem.MedtrackCategoryChip
import com.naveenhospital.medtrack.core.designsystem.MedtrackCategoryTile
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.designsystem.MedtrackCompactCard
import com.naveenhospital.medtrack.core.designsystem.MedtrackIconBadge
import com.naveenhospital.medtrack.core.designsystem.MedtrackMiniPill
import com.naveenhospital.medtrack.core.designsystem.MedtrackPage
import com.naveenhospital.medtrack.core.designsystem.MedtrackPullRefreshBox
import com.naveenhospital.medtrack.core.designsystem.MedtrackRiskFlag
import com.naveenhospital.medtrack.core.designsystem.MedtrackSectionEyebrow
import com.naveenhospital.medtrack.core.designsystem.MedtrackStatusPill
import com.naveenhospital.medtrack.core.designsystem.MedtrackType
import com.naveenhospital.medtrack.core.designsystem.medtrackCategoryVisual
import com.naveenhospital.medtrack.core.designsystem.medtrackShortDateLabel
import com.naveenhospital.medtrack.core.domain.model.CaseCategory
import com.naveenhospital.medtrack.core.domain.model.PatientCase
import com.naveenhospital.medtrack.core.domain.model.PatientTask
import com.naveenhospital.medtrack.core.domain.model.PatientVital
import com.naveenhospital.medtrack.core.domain.model.TaskFormMetadata
import com.naveenhospital.medtrack.core.domain.model.VitalStatusResult
import com.naveenhospital.medtrack.core.domain.model.VitalsThresholdConfig
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import kotlin.math.absoluteValue
import kotlin.math.roundToInt


@Composable
@OptIn(ExperimentalLayoutApi::class)
fun CaseListScreen(
    cases: List<PatientCase>,
    isRefreshing: Boolean = false,
    error: String? = null,
    onRefresh: () -> Unit = {},
    onCallPatient: (PatientCase) -> Unit,
    onOpenCase: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    var query by rememberSaveable { mutableStateOf("") }
    var filter by rememberSaveable { mutableStateOf("all") }
    var expandedCaseId by rememberSaveable { mutableStateOf<String?>(null) }
    val chipScrollState = rememberScrollState()
    val dedupedCases = cases.distinctBy { it.dedupeKey() }
    val redCaseCount = remember(dedupedCases) { dedupedCases.count { it.isHighRisk } }
    val visibleCases = dedupedCases
        .filter { it.matchesCaseSearch(query) }
        .filter { it.matchesCaseFilter(filter) }
    val effectiveExpandedCaseId = expandedCaseId

    Column(
        modifier = modifier
            .background(MedtrackColors.Surface)
            .padding(horizontal = 18.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Top,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    text = "Cases",
                    color = MedtrackColors.Ink,
                    style = MaterialTheme.typography.headlineSmall.copy(fontSize = 24.sp),
                    fontWeight = FontWeight.ExtraBold,
                )
                Text(
                    text = "${cases.size} active records",
                    color = MedtrackColors.Muted,
                    style = MaterialTheme.typography.labelMedium.copy(fontSize = 13.sp),
                    fontWeight = FontWeight.SemiBold,
                )
            }
            SyncStatusPill(
                isRefreshing = isRefreshing,
                onRefresh = onRefresh,
            )
        }
        error?.let { Text(text = it, color = MedtrackColors.Danger) }
        if (isRefreshing) {
            Text(text = "Refreshing", color = MedtrackColors.Muted)
        }
        CasesSearchBar(
            value = query,
            onValueChange = { query = it },
        )
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(chipScrollState),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            CaseFilterChip(label = "All", count = cases.size, selected = filter == "all") { filter = "all" }
            CaseFilterChip(label = "Red flag", count = redCaseCount, selected = filter == "red") { filter = "red" }
            CaseFilterChip(label = "ANC", selected = filter == "anc") { filter = "anc" }
            CaseFilterChip(label = "Medicine", selected = filter == "medicine") { filter = "medicine" }
            CaseFilterChip(label = "Surgery", selected = filter == "surgery") { filter = "surgery" }
        }
        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(11.dp),
            contentPadding = PaddingValues(bottom = 104.dp),
        ) {
            if (visibleCases.isEmpty() && !isRefreshing) {
                item {
                    MedtrackCompactCard {
                        Text("No matching cases", color = MedtrackColors.Muted)
                    }
                }
            }
            items(visibleCases, key = { it.id }) { patientCase ->
                CaseRow(
                    patientCase = patientCase,
                    expanded = effectiveExpandedCaseId == patientCase.id,
                    onToggle = {
                        expandedCaseId = if (effectiveExpandedCaseId == patientCase.id) null else patientCase.id
                    },
                    onCallPatient = { onCallPatient(patientCase) },
                    onOpenCase = { onOpenCase(patientCase.id) },
                )
            }
        }
    }
}

@Composable
fun CaseDetailScreen(
    caseId: String,
    patientCase: PatientCase?,
    tasks: List<PatientTask>,
    vitals: List<PatientVital>,
    vitalsThresholds: VitalsThresholdConfig?,
    actionMessage: String?,
    isRefreshing: Boolean,
    error: String?,
    onRefresh: () -> Unit,
    onCompleteTask: (PatientTask) -> Unit,
    onAddVitals: (VitalsEntryInput) -> Unit,
    onCallPatient: (PatientCase) -> Unit,
    onMessagePatient: (PatientCase) -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    canEditCase: Boolean = false,
    canCreateTask: Boolean = false,
    canEditTask: Boolean = false,
    taskMetadata: TaskFormMetadata? = null,
    onEditCase: () -> Unit = {},
    onTaskAction: (TaskSheetAction, String?, (String?) -> Unit) -> Unit = { _, _, cb -> cb(null) },
    onEditVitals: (String, VitalsEntryInput) -> Unit = { _, _ -> },
) {
    var showVitalsDialog by rememberSaveable { mutableStateOf(false) }
    var editingVital by remember(caseId) { mutableStateOf<PatientVital?>(null) }
    var taskSheetTarget by remember(caseId) { mutableStateOf<TaskSheetTarget?>(null) }
    val listState = rememberLazyListState()

    Column(
        modifier = modifier
            .background(MedtrackColors.Surface)
            .padding(horizontal = 10.dp, vertical = 6.dp),
        verticalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            CaseHeaderIconButton(onClick = onBack) {
                Icon(imageVector = Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back", tint = MedtrackColors.Ink)
            }
            Text(
                text = patientCase?.patientName ?: "Case $caseId",
                color = MedtrackColors.Ink,
                style = MaterialTheme.typography.titleMedium.copy(fontSize = 17.sp),
                fontWeight = FontWeight.ExtraBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier
                    .weight(1f)
                    .padding(horizontal = 10.dp),
            )
            if (canEditCase) {
                CaseHeaderIconButton(onClick = onEditCase) {
                    Icon(imageVector = Icons.Outlined.Edit, contentDescription = "Edit case", tint = MedtrackColors.Ink)
                }
                Spacer(modifier = Modifier.width(8.dp))
            }
            CaseHeaderIconButton(onClick = onRefresh) {
                Icon(imageVector = Icons.Outlined.Refresh, contentDescription = "Refresh", tint = MedtrackColors.Ink)
            }
        }

        error?.let { Text(text = it, color = MedtrackColors.Danger) }
        actionMessage?.let { Text(text = it, color = MedtrackColors.Muted) }
        if (isRefreshing) {
            Text(text = "Refreshing", color = MedtrackColors.Muted)
        }

        MedtrackPullRefreshBox(
            modifier = Modifier.weight(1f),
            isRefreshing = isRefreshing,
            onRefresh = onRefresh,
            canRefresh = { listState.firstVisibleItemIndex == 0 && listState.firstVisibleItemScrollOffset == 0 },
        ) {
            LazyColumn(
                state = listState,
                verticalArrangement = Arrangement.spacedBy(9.dp),
                contentPadding = PaddingValues(bottom = if (patientCase == null) 20.dp else 96.dp),
            ) {
                if (patientCase == null) {
                    item {
                        MedtrackCompactCard {
                            Text(text = "Case details will appear after the inbox syncs.", color = MedtrackColors.Muted)
                        }
                    }
                } else {
                    item {
                        CaseHero(
                            patientCase = patientCase,
                        )
                    }
                    val latestVitalsSummary = vitals.firstOrNull()?.summary?.takeIf { it.isNotBlank() }
                        ?: patientCase.latestVitalSummary?.takeIf { it.isNotBlank() }
                    if (latestVitalsSummary != null) {
                        item {
                            LatestVitalsStrip(
                                summary = latestVitalsSummary,
                                recordedAt = vitals.firstOrNull()?.recordedAt,
                                onAddVitals = { showVitalsDialog = true },
                            )
                        }
                    }
                    val overdueTasks = tasks.filter { it.taskGroup() == TaskGroup.OVERDUE }
                    val upcomingTasks = tasks.filter { it.taskGroup() == TaskGroup.UPCOMING }
                    val doneTasks = tasks.filter { it.taskGroup() == TaskGroup.DONE }
                    val openTaskCount = tasks.count { it.isActionable() }
                    val doneTaskCount = doneTasks.size
                    val onEditTask: ((PatientTask) -> Unit)? =
                        if (canEditTask) { task -> taskSheetTarget = TaskSheetTarget.Edit(task) } else null
                    item {
                        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                            Box(modifier = Modifier.weight(1f)) {
                                MedtrackSectionEyebrow(
                                    title = "Tasks",
                                    trailing = "$openTaskCount open \u00B7 $doneTaskCount done",
                                )
                            }
                            if (canCreateTask) {
                                AddTaskChip(onClick = { taskSheetTarget = TaskSheetTarget.Create })
                            }
                        }
                    }
                    if (tasks.isEmpty()) {
                        item {
                            MedtrackCompactCard {
                                Text(text = "No tasks recorded", color = MedtrackColors.Muted)
                            }
                        }
                    } else {
                        if (overdueTasks.isNotEmpty()) {
                            item {
                                TaskSectionCard(title = "Overdue", tasks = overdueTasks, onCompleteTask = onCompleteTask, onEditTask = onEditTask)
                            }
                        }
                        if (upcomingTasks.isNotEmpty()) {
                            item {
                                TaskSectionCard(title = "Upcoming", tasks = upcomingTasks, onCompleteTask = onCompleteTask, onEditTask = onEditTask)
                            }
                        }
                        if (doneTasks.isNotEmpty()) {
                            item {
                                TaskSectionCard(title = "Done", tasks = doneTasks, onCompleteTask = onCompleteTask, onEditTask = onEditTask)
                            }
                        }
                    }
                    item {
                        VitalsHistoryCard(
                            vitals = vitals,
                            fallback = patientCase.latestVitalSummary,
                            onEditVital = if (canEditTask) {
                                { vital -> editingVital = vital; showVitalsDialog = true }
                            } else {
                                null
                            },
                        )
                    }
                }
            }
        }

        patientCase?.let {
            CaseStickyActions(
                patientCase = it,
                onCallPatient = { onCallPatient(it) },
                onMessagePatient = { onMessagePatient(it) },
                onAddVitals = { showVitalsDialog = true },
            )
        }
    }

    if (showVitalsDialog) {
        val vitalBeingEdited = editingVital
        VitalsEntrySheet(
            patientCase = patientCase,
            thresholds = vitalsThresholds,
            existingVital = vitalBeingEdited,
            onDismiss = {
                showVitalsDialog = false
                editingVital = null
            },
            onSubmit = { input ->
                showVitalsDialog = false
                editingVital = null
                if (vitalBeingEdited != null) {
                    onEditVitals(vitalBeingEdited.id, input)
                } else {
                    onAddVitals(input)
                }
            },
        )
    }

    taskSheetTarget?.let { target ->
        val editingTask = (target as? TaskSheetTarget.Edit)?.task
        TaskEditorSheet(
            metadata = taskMetadata,
            existingTask = editingTask,
            onDismiss = { taskSheetTarget = null },
            onSubmit = { action, report ->
                onTaskAction(action, editingTask?.id) { error ->
                    report(error)
                    if (error == null && action !is TaskSheetAction.Note) {
                        taskSheetTarget = null
                    }
                }
            },
        )
    }
}

private sealed interface TaskSheetTarget {
    data object Create : TaskSheetTarget
    data class Edit(val task: PatientTask) : TaskSheetTarget
}

@Composable
private fun AddTaskChip(onClick: () -> Unit) {
    Surface(
        modifier = Modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(999.dp),
        color = MedtrackColors.PrimarySoft,
        border = BorderStroke(1.dp, MedtrackColors.Primary.copy(alpha = 0.28f)),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 11.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Outlined.Add, contentDescription = null, tint = MedtrackColors.Primary, modifier = Modifier.size(16.dp))
            Text(
                text = "Add",
                color = MedtrackColors.Primary,
                style = MaterialTheme.typography.labelMedium.copy(fontSize = 12.5.sp),
                fontWeight = FontWeight.ExtraBold,
            )
        }
    }
}

@Composable
private fun CaseHeaderIconButton(
    onClick: () -> Unit,
    content: @Composable () -> Unit,
) {
    Surface(
        modifier = Modifier.size(42.dp),
        shape = RoundedCornerShape(13.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border),
    ) {
        Box(
            modifier = Modifier.clickable(onClick = onClick),
            contentAlignment = Alignment.Center,
        ) {
            content()
        }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun CaseHero(
    patientCase: PatientCase,
) {
    val visual = medtrackCategoryVisual(patientCase.category.name, patientCase.categoryLabel)
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border),
        shadowElevation = 3.dp,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(
                    Brush.verticalGradient(
                        listOf(visual.soft.copy(alpha = 0.42f), MedtrackColors.Card),
                    ),
                )
                .height(IntrinsicSize.Min),
        ) {
            Box(
                modifier = Modifier
                    .fillMaxHeight()
                    .width(5.dp)
                    .background(visual.tint),
            )
            Column(
                modifier = Modifier
                    .weight(1f)
                    .padding(horizontal = 13.dp, vertical = 11.dp),
                verticalArrangement = Arrangement.spacedBy(7.dp),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.Top,
                ) {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                        MedtrackCategoryTile(
                            iconResId = visual.iconResId,
                            tint = visual.tint,
                            softColor = visual.soft,
                            size = 44.dp,
                            radius = 14.dp,
                        )
                        Column(verticalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.weight(1f)) {
                            Text(
                                text = patientCase.patientName,
                                color = MedtrackColors.Ink,
                                style = MaterialTheme.typography.titleMedium.copy(fontSize = 19.sp),
                                fontWeight = FontWeight.ExtraBold,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                            )
                            Text(
                                text = patientCase.identityLine(),
                                color = MedtrackColors.Muted,
                                style = MaterialTheme.typography.bodySmall.copy(fontFamily = MedtrackType.Mono),
                                fontWeight = FontWeight.Medium,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                    }
                    if (patientCase.isHighRisk) {
                        MedtrackRiskFlag(count = patientCase.riskReasonCount())
                    }
                }

                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    HeroPill(patientCase.categoryLabel, visual.tint)
                    patientCase.subcategoryLabel?.takeIf { it.isNotBlank() }?.let { HeroPill(it, visual.tint) }
                    HeroPill(patientCase.status.label, patientCase.statusColor())
                }

                Text(
                    text = patientCase.diagnosis.ifBlank { "Case details" },
                    color = MedtrackColors.InkSoft,
                    style = MaterialTheme.typography.labelLarge.copy(fontSize = 14.sp),
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun HeroPill(text: String, color: Color) {
    Surface(
        shape = RoundedCornerShape(50),
        color = color.copy(alpha = 0.11f),
        border = BorderStroke(1.dp, color.copy(alpha = 0.2f)),
    ) {
        Text(
            text = text,
            color = color,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun CaseStickyActions(
    patientCase: PatientCase,
    onCallPatient: () -> Unit,
    onMessagePatient: () -> Unit,
    onAddVitals: () -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.BorderSoft),
        shadowElevation = 4.dp,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 7.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Button(
                onClick = onCallPatient,
                enabled = !patientCase.phoneNumber.isNullOrBlank(),
                modifier = Modifier
                    .weight(0.86f)
                    .height(42.dp),
                colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Success),
                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 0.dp),
            ) {
                Icon(imageVector = Icons.Outlined.Phone, contentDescription = null, modifier = Modifier.size(14.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text("Call", fontWeight = FontWeight.ExtraBold, style = MaterialTheme.typography.labelLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Button(
                onClick = onMessagePatient,
                enabled = !patientCase.phoneNumber.isNullOrBlank(),
                modifier = Modifier
                    .weight(1.22f)
                    .height(42.dp),
                colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.SuccessSoft, contentColor = MedtrackColors.Success),
                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 0.dp),
            ) {
                Icon(imageVector = Icons.AutoMirrored.Outlined.Chat, contentDescription = null, modifier = Modifier.size(14.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text("WhatsApp", fontWeight = FontWeight.ExtraBold, style = MaterialTheme.typography.labelLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Button(
                onClick = onAddVitals,
                modifier = Modifier
                    .weight(0.92f)
                    .height(42.dp),
                colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Ink),
                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 0.dp),
            ) {
                Icon(imageVector = Icons.Outlined.Add, contentDescription = null, modifier = Modifier.size(14.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text("Vitals", fontWeight = FontWeight.ExtraBold, style = MaterialTheme.typography.labelLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

@Composable
private fun LatestVitalsStrip(
    summary: String,
    recordedAt: String?,
    onAddVitals: () -> Unit,
) {
    val dateLabel = recordedAt.caseDetailShortDateLabel()
    Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
        MedtrackSectionEyebrow(title = "Latest vitals", trailing = dateLabel)
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            color = MedtrackColors.Card,
            border = BorderStroke(1.dp, MedtrackColors.Border),
            shadowElevation = 1.dp,
        ) {
            Box(modifier = Modifier.padding(12.dp)) {
                CompactVitalsStrip(summary = summary, onAddVitals = onAddVitals)
            }
        }
    }
}

@Composable
private fun VitalsHistoryCard(
    vitals: List<PatientVital>,
    fallback: String?,
    onEditVital: ((PatientVital) -> Unit)? = null,
) {
    Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
        MedtrackSectionEyebrow(
            title = "Vitals",
            trailing = "${vitals.size} records",
        )
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(14.dp),
            color = MedtrackColors.Card,
            border = BorderStroke(1.dp, MedtrackColors.Border),
        ) {
            Column(modifier = Modifier.padding(horizontal = 14.dp, vertical = 4.dp)) {
                if (vitals.isEmpty()) {
                    Text(
                        text = fallback ?: "No vitals recorded",
                        color = MedtrackColors.Muted,
                        modifier = Modifier.padding(vertical = 9.dp),
                        style = MaterialTheme.typography.labelMedium,
                    )
                } else {
                    vitals.take(2).forEachIndexed { index, vital ->
                        VitalsRow(vital = vital, showDivider = index > 0, onEditVital = onEditVital)
                    }
                }
            }
        }
    }
}

@Composable
private fun TaskSectionCard(
    title: String,
    tasks: List<PatientTask>,
    onCompleteTask: (PatientTask) -> Unit,
    onEditTask: ((PatientTask) -> Unit)? = null,
) {
    Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
        Text(
            text = title,
            color = if (title.equals("Done", ignoreCase = true)) MedtrackColors.Success else MedtrackColors.Muted,
            style = MaterialTheme.typography.labelSmall.copy(fontSize = 11.5.sp),
            fontWeight = FontWeight.ExtraBold,
            letterSpacing = 0.4.sp,
            modifier = Modifier.padding(horizontal = 2.dp),
        )
        tasks.forEach { task ->
            TaskRow(task = task, onCompleteTask = onCompleteTask, onEditTask = onEditTask)
        }
    }
}

@Composable
private fun TaskRow(
    task: PatientTask,
    onCompleteTask: (PatientTask) -> Unit,
    onEditTask: ((PatientTask) -> Unit)? = null,
) {
    val actionable = task.isActionable()
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .then(if (onEditTask != null) Modifier.clickable { onEditTask(task) } else Modifier),
        shape = RoundedCornerShape(12.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 9.dp, vertical = 7.dp),
            horizontalArrangement = Arrangement.spacedBy(9.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            MedtrackIconBadge(
                icon = if (actionable) Icons.Outlined.CalendarMonth else Icons.Outlined.CheckCircle,
                tint = task.statusColor(),
                modifier = Modifier.size(30.dp),
            )
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    text = task.title,
                    color = if (actionable) MedtrackColors.Ink else MedtrackColors.Muted,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.labelLarge.copy(fontSize = 13.5.sp),
                    maxLines = if (actionable) 2 else 1,
                    overflow = TextOverflow.Ellipsis,
                    textDecoration = if (actionable) TextDecoration.None else TextDecoration.LineThrough,
                )
                Text(
                    text = task.dueDate.caseDetailTaskDateLabel() ?: "No due date",
                    color = MedtrackColors.Muted,
                    style = MaterialTheme.typography.labelMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            if (actionable) {
                MedtrackMiniPill(text = task.statusLabel, color = task.statusColor())
            } else {
                MedtrackMiniPill(text = task.statusLabel, color = MedtrackColors.Success)
            }
            Surface(
                modifier = Modifier
                    .size(30.dp)
                    .clickable(enabled = actionable) {
                        onCompleteTask(task)
                    },
                shape = RoundedCornerShape(50),
                color = if (actionable) MedtrackColors.Card else MedtrackColors.Success.copy(alpha = 0.12f),
                border = BorderStroke(1.5.dp, if (actionable) MedtrackColors.Border else MedtrackColors.Success.copy(alpha = 0.32f)),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    if (!actionable) {
                        Icon(imageVector = Icons.Outlined.CheckCircle, contentDescription = null, tint = MedtrackColors.Success, modifier = Modifier.size(18.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun VitalsRow(vital: PatientVital, showDivider: Boolean, onEditVital: ((PatientVital) -> Unit)? = null) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .then(if (onEditVital != null) Modifier.clickable { onEditVital(vital) } else Modifier)
            .then(if (showDivider) Modifier.background(MedtrackColors.Card) else Modifier)
            .padding(vertical = 9.dp),
        horizontalArrangement = Arrangement.spacedBy(9.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(imageVector = Icons.Outlined.Favorite, contentDescription = null, tint = MedtrackColors.Medicine, modifier = Modifier.size(16.dp))
        Text(
            text = vital.summary.ifBlank { "Vitals recorded" },
            color = MedtrackColors.Ink,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.labelMedium,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        Text(
            text = vital.recordedAt.caseDetailShortDateLabel() ?: vital.recordedAt,
            color = MedtrackColors.Faint,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
        )
    }
}

private fun String?.caseDetailShortDateLabel(): String? {
    val parsed = parseCaseDueDate() ?: return this?.takeIf { it.isNotBlank() }?.let { medtrackShortDateLabel(it) ?: it }
    return SimpleDateFormat("dd MMM", Locale.US).format(parsed)
}

private fun String?.caseDetailTaskDateLabel(): String? {
    val parsed = parseCaseDueDate() ?: return this?.takeIf { it.isNotBlank() }?.let { medtrackShortDateLabel(it) ?: it }
    return SimpleDateFormat("dd MMM yyyy", Locale.US).format(parsed)
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun VitalsThresholdFeedback(
    thresholds: VitalsThresholdConfig?,
    systolic: Int?,
    diastolic: Int?,
    pulse: Double?,
    spo2: Double?,
    weight: Double?,
    hemoglobin: Double?,
) {
    if (thresholds == null) return
    val feedback = buildList {
        if (systolic != null || diastolic != null) add("BP" to thresholds.evaluateBloodPressure(systolic, diastolic))
        if (pulse != null) add("PR" to thresholds.evaluateMetric("pr", pulse))
        if (spo2 != null) add("SpO2" to thresholds.evaluateMetric("spo2", spo2))
        if (weight != null) add("Wt" to thresholds.evaluateMetric("weight", weight))
        if (hemoglobin != null) add("Hb" to thresholds.evaluateMetric("hemoglobin", hemoglobin))
    }.filter { (_, result) -> result.status != "na" }
    if (feedback.isEmpty()) return

    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
        feedback.forEach { (label, result) ->
            VitalsFeedbackChip(
                text = "$label ${result.label}",
                result = result,
            )
        }
    }
}

@Composable
private fun VitalsFeedbackChip(text: String, result: VitalStatusResult) {
    Surface(
        shape = RoundedCornerShape(999.dp),
        color = result.statusSoftColor(),
        contentColor = result.statusColor(),
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp),
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.ExtraBold,
        )
    }
}

private fun VitalStatusResult.statusSoftColor(): Color =
    when (status.lowercase(Locale.ROOT)) {
        "green" -> MedtrackColors.VitalOkSoft
        "orange", "neutral" -> MedtrackColors.VitalHighSoft
        "red" -> MedtrackColors.VitalCriticalSoft
        else -> MedtrackColors.Faint
    }

@Composable
private fun SyncStatusPill(
    isRefreshing: Boolean,
    onRefresh: () -> Unit,
) {
    val label = if (isRefreshing) "Syncing" else "Synced"
    val color = if (isRefreshing) MedtrackColors.Primary else MedtrackColors.Success
    Surface(
        modifier = Modifier.clickable(onClick = onRefresh),
        shape = RoundedCornerShape(999.dp),
        color = if (isRefreshing) MedtrackColors.PrimarySoft else MedtrackColors.SuccessSoft,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 11.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(5.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = Icons.Outlined.CloudDone,
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(15.dp),
            )
            Text(
                text = label,
                color = color,
                style = MaterialTheme.typography.labelMedium.copy(fontSize = 12.5.sp),
                fontWeight = FontWeight.Bold,
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun CasesSearchBar(
    value: String,
    onValueChange: (String) -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 11.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = Icons.Outlined.Search,
                contentDescription = null,
                tint = MedtrackColors.Faint,
                modifier = Modifier.size(20.dp),
            )
            BasicTextField(
                value = value,
                onValueChange = onValueChange,
                singleLine = true,
                textStyle = MaterialTheme.typography.bodyMedium.copy(
                    color = MedtrackColors.Ink,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Medium,
                ),
                modifier = Modifier.weight(1f),
                decorationBox = { innerTextField ->
                    Box {
                        if (value.isBlank()) {
                            Text(
                                text = "Search patient, UHID, phone",
                                color = MedtrackColors.Faint,
                                style = MaterialTheme.typography.bodyMedium.copy(fontSize = 15.sp),
                                fontWeight = FontWeight.Medium,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                        innerTextField()
                    }
                },
            )
        }
    }
}

@Composable
private fun CaseFilterChip(label: String, selected: Boolean, count: Int? = null, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(999.dp),
        color = if (selected) MedtrackColors.Primary else MedtrackColors.Card,
        border = BorderStroke(1.dp, if (selected) MedtrackColors.Primary else MedtrackColors.Border),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 13.dp, vertical = 7.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = label,
                color = if (selected) Color.White else MedtrackColors.Ink,
                style = MaterialTheme.typography.labelMedium.copy(fontSize = 13.sp),
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            count?.let {
                Text(
                    text = it.toString(),
                    color = if (selected) Color.White else MedtrackColors.Faint,
                    style = MaterialTheme.typography.labelSmall.copy(fontSize = 11.sp),
                    fontWeight = FontWeight.ExtraBold,
                    maxLines = 1,
                )
            }
        }
    }
}

@Composable
private fun CaseRow(
    patientCase: PatientCase,
    expanded: Boolean,
    onToggle: () -> Unit,
    onCallPatient: () -> Unit,
    onOpenCase: () -> Unit,
) {
    var dragOffset by rememberSaveable(patientCase.id) { mutableStateOf(0f) }
    val density = LocalDensity.current
    val swipeThreshold = with(density) { 40.dp.toPx() }
    val maxDrag = with(density) { 96.dp.toPx() }
    val canCall = !patientCase.phoneNumber.isNullOrBlank()
    val visual = medtrackCategoryVisual(patientCase.category.name, patientCase.categoryLabel)
    val railColor = if (patientCase.isHighRisk) MedtrackColors.Danger else MedtrackColors.Border

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .pointerInput(patientCase.id) {
                detectTapGestures(
                    onTap = {
                        if (dragOffset != 0f) {
                            dragOffset = 0f
                        } else {
                            onToggle()
                        }
                    },
                )
            }
            .pointerInput(patientCase.id, patientCase.phoneNumber, swipeThreshold, maxDrag) {
                detectHorizontalDragGestures(
                    onDragCancel = { dragOffset = 0f },
                    onDragEnd = {
                        dragOffset = when {
                            dragOffset <= -swipeThreshold && canCall -> -maxDrag
                            dragOffset >= swipeThreshold -> maxDrag
                            else -> 0f
                        }
                    },
                    onHorizontalDrag = { change, dragAmount ->
                        change.consume()
                        dragOffset = (dragOffset + dragAmount).coerceIn(-maxDrag, maxDrag)
                    },
                )
            },
    ) {
        CasesSwipeActionBackground(
            dragOffset = dragOffset,
            canCall = canCall,
            onCallPatient = {
                dragOffset = 0f
                onCallPatient()
            },
            onOpenCase = {
                dragOffset = 0f
                onOpenCase()
            },
        )
        Surface(
            modifier = Modifier.offset { IntOffset(dragOffset.roundToInt(), 0) },
            shape = RoundedCornerShape(16.dp),
            color = MedtrackColors.Card,
            border = BorderStroke(1.dp, if (expanded) railColor.copy(alpha = 0.34f) else MedtrackColors.Border),
            shadowElevation = if (expanded) 7.dp else 1.dp,
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(IntrinsicSize.Min),
            ) {
                Box(
                    modifier = Modifier
                        .width(4.dp)
                        .fillMaxHeight()
                        .background(railColor),
                )
                Column(modifier = Modifier.weight(1f)) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 13.dp, vertical = 12.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        MedtrackCategoryTile(
                            iconResId = visual.iconResId,
                            tint = visual.tint,
                            softColor = visual.soft,
                            size = 42.dp,
                            radius = 12.dp,
                        )
                        Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                            Text(
                                text = patientCase.patientName,
                                color = MedtrackColors.Ink,
                                style = MaterialTheme.typography.titleSmall.copy(fontSize = 15.5.sp),
                                fontWeight = FontWeight.ExtraBold,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                            )
                            Text(
                                text = patientCase.caseListIdentityLine(),
                                color = MedtrackColors.Faint,
                                style = MaterialTheme.typography.labelSmall.copy(fontFamily = MedtrackType.Mono, fontSize = 11.5.sp),
                                fontWeight = FontWeight.Medium,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                            )
                            Text(
                                text = patientCase.diagnosis,
                                color = MedtrackColors.Muted,
                                style = MaterialTheme.typography.bodySmall.copy(fontSize = 13.5.sp),
                                fontWeight = FontWeight.SemiBold,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(9.dp),
                        ) {
                            if (patientCase.isHighRisk) {
                                CompactRiskFlag(count = patientCase.riskReasonCount())
                            }
                            Icon(
                                imageVector = Icons.Outlined.ExpandMore,
                                contentDescription = if (expanded) "Collapse case" else "Expand case",
                                tint = MedtrackColors.Faint,
                                modifier = Modifier
                                    .size(20.dp)
                                    .graphicsLayer(rotationZ = if (expanded) 180f else 0f),
                            )
                        }
                    }

                    if (expanded) {
                        ExpandedCaseTray(
                            patientCase = patientCase,
                            onOpenCase = onOpenCase,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun BoxScope.CasesSwipeActionBackground(
    dragOffset: Float,
    canCall: Boolean,
    onCallPatient: () -> Unit,
    onOpenCase: () -> Unit,
) {
    if (dragOffset == 0f) return

    val isCall = dragOffset < 0f
    val enabled = !isCall || canCall
    val alignment = if (isCall) Alignment.CenterEnd else Alignment.CenterStart
    val color = when {
        !enabled -> MedtrackColors.Muted.copy(alpha = 0.36f)
        isCall -> MedtrackColors.Success
        else -> MedtrackColors.Primary
    }
    val icon = if (isCall) Icons.Outlined.Phone else Icons.AutoMirrored.Outlined.OpenInNew
    val label = if (isCall) "Call" else "Open"
    val action = if (isCall) onCallPatient else onOpenCase

    Box(
        modifier = Modifier
            .matchParentSize()
            .background(MedtrackColors.SurfaceAlt, shape = RoundedCornerShape(16.dp))
            .padding(horizontal = 8.dp, vertical = 7.dp),
        contentAlignment = alignment,
    ) {
        Surface(
            modifier = Modifier
                .width(80.dp)
                .height(88.dp)
                .clickable(enabled = enabled, onClick = action),
            shape = RoundedCornerShape(16.dp),
            color = color,
            shadowElevation = if (enabled) 2.dp else 0.dp,
        ) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = label,
                    tint = Color.White,
                    modifier = Modifier.size(19.dp),
                )
                Text(
                    text = label,
                    color = Color.White,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }
    }
}

@Composable
private fun CompactRiskFlag(count: Int) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = Icons.Outlined.Flag,
            contentDescription = "Red flag",
            tint = MedtrackColors.Danger,
            modifier = Modifier.size(17.dp),
        )
        Text(
            text = count.toString(),
            color = MedtrackColors.Danger,
            style = MaterialTheme.typography.labelMedium.copy(fontSize = 13.5.sp),
            fontWeight = FontWeight.ExtraBold,
            maxLines = 1,
        )
    }
}

@Composable
private fun ExpandedCaseTray(
    patientCase: PatientCase,
    onOpenCase: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(MedtrackColors.Card)
            .padding(start = 13.dp, end = 13.dp, bottom = 13.dp),
        verticalArrangement = Arrangement.spacedBy(11.dp),
    ) {
        Spacer(
            modifier = Modifier
                .fillMaxWidth()
                .height(1.dp)
                .background(MedtrackColors.BorderSoft),
        )
        Row(
            horizontalArrangement = Arrangement.spacedBy(9.dp),
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth(),
        ) {
            DuePill(patientCase.nextTaskDueDate)
        }
        CompactVitalsStrip(summary = patientCase.latestVitalSummary, onAddVitals = onOpenCase)
        Button(
            onClick = onOpenCase,
            modifier = Modifier
                .fillMaxWidth()
                .height(46.dp),
            shape = RoundedCornerShape(13.dp),
            colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Primary),
            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 0.dp),
        ) {
            Icon(
                imageVector = Icons.AutoMirrored.Outlined.OpenInNew,
                contentDescription = null,
                modifier = Modifier.size(18.dp),
            )
            Spacer(modifier = Modifier.width(7.dp))
            Text(
                text = "Open full case",
                fontWeight = FontWeight.ExtraBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun DuePill(dueDate: String?) {
    val state = dueDate.caseDueState()
    Surface(
        shape = RoundedCornerShape(999.dp),
        color = state.background,
        border = BorderStroke(1.dp, state.color.copy(alpha = 0.22f)),
    ) {
        Text(
            text = state.label,
            color = state.color,
            style = MaterialTheme.typography.labelMedium.copy(fontSize = 12.5.sp),
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            modifier = Modifier.padding(horizontal = 9.dp, vertical = 4.dp),
        )
    }
}

@Composable
private fun CompactVitalsStrip(
    summary: String?,
    onAddVitals: (() -> Unit)? = null,
) {
    val metrics = summary?.latestVitalPairs() ?: emptyList()
    Row(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier
            .fillMaxWidth()
            .height(IntrinsicSize.Max),
    ) {
        listOf("BP", "Pulse", "SpO\u2082", "Hb").forEachIndexed { index, label ->
            val metric = metrics.getOrNull(index)
            val value = metric?.value?.takeIf { it != "\u2014" }
            val tone = metric.vitalTone()
            Surface(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxHeight()
                    .clickable(enabled = value == null && onAddVitals != null) { onAddVitals?.invoke() },
                shape = RoundedCornerShape(12.dp),
                color = tone.background,
                border = if (value == null) BorderStroke(1.dp, MedtrackColors.Border) else null,
            ) {
                Column(
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        if (value != null) {
                            Box(
                                modifier = Modifier
                                    .size(6.dp)
                                    .background(tone.color, RoundedCornerShape(999.dp)),
                            )
                        }
                        Text(
                            text = label,
                            color = tone.color,
                            style = MaterialTheme.typography.labelSmall.copy(fontSize = 10.5.sp),
                            fontWeight = FontWeight.ExtraBold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    Text(
                        text = value ?: "+ Add",
                        color = if (value == null) MedtrackColors.Primary else MedtrackColors.Ink,
                        style = MaterialTheme.typography.labelMedium.copy(fontSize = if (value == null) 12.sp else 13.sp),
                        fontWeight = FontWeight.ExtraBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    metric?.unit?.takeIf { it.isNotBlank() && value != null }?.let {
                        Text(
                            text = it,
                            color = MedtrackColors.Muted,
                            style = MaterialTheme.typography.labelSmall.copy(fontSize = 10.5.sp),
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
        }
    }
}

private data class CaseDueState(
    val label: String,
    val color: Color,
    val background: Color,
)

private fun String?.caseDueState(): CaseDueState {
    val parsed = parseCaseDueDate()
    if (parsed == null) {
        return CaseDueState("No due", MedtrackColors.Muted, MedtrackColors.BorderSoft)
    }
    val today = Calendar.getInstance()
    val due = Calendar.getInstance().apply { time = parsed }
    val delta = due.dayNumber() - today.dayNumber()
    return when {
        delta == 0 -> CaseDueState("Due today", MedtrackColors.Primary, MedtrackColors.PrimarySoft)
        delta == 1 -> CaseDueState("Tomorrow", MedtrackColors.Primary, MedtrackColors.PrimarySoft)
        delta > 1 -> CaseDueState("Upcoming", MedtrackColors.Muted, MedtrackColors.BorderSoft)
        delta == -1 -> CaseDueState("Overdue 1 day", MedtrackColors.Danger, MedtrackColors.DangerSoft)
        delta.absoluteValue <= 7 -> CaseDueState("Overdue ${delta.absoluteValue} days", MedtrackColors.Danger, MedtrackColors.DangerSoft)
        else -> CaseDueState("Overdue", MedtrackColors.Danger, MedtrackColors.DangerSoft)
    }
}

private fun String?.parseCaseDueDate(): Date? {
    val value = this?.trim()?.takeIf { it.isNotBlank() }?.replace(Regex("""(\.\d{3})\d+"""), "$1") ?: return null
    val patterns = listOf(
        CaseDatePattern("yyyy-MM-dd'T'HH:mm:ss.SSSXXX"),
        CaseDatePattern("yyyy-MM-dd'T'HH:mm:ssXXX"),
        CaseDatePattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", utc = true),
        CaseDatePattern("yyyy-MM-dd'T'HH:mm:ss'Z'", utc = true),
        CaseDatePattern("yyyy-MM-dd HH:mm:ss"),
        CaseDatePattern("yyyy-MM-dd"),
    )
    return patterns.firstNotNullOfOrNull { pattern ->
        runCatching {
            SimpleDateFormat(pattern.value, Locale.US).apply {
                isLenient = false
                if (pattern.utc) timeZone = TimeZone.getTimeZone("UTC")
            }.parse(value)
        }.getOrNull()
    }
}

private data class CaseDatePattern(
    val value: String,
    val utc: Boolean = false,
)

private fun Calendar.dayNumber(): Int =
    get(Calendar.YEAR) * 366 + get(Calendar.DAY_OF_YEAR)

private data class VitalTone(
    val color: Color,
    val background: Color,
)

private fun LatestVitalMetric?.vitalTone(): VitalTone {
    if (this == null || value == "\u2014") return VitalTone(MedtrackColors.Faint, MedtrackColors.Surface)
    val normalized = label.replace("\u2082", "2").lowercase()
    return when (normalized) {
        "bp" -> {
            val numbers = value.split("/", " ").mapNotNull { it.toIntOrNull() }
            val systolic = numbers.getOrNull(0)
            val diastolic = numbers.getOrNull(1)
            when {
                systolic != null && systolic >= 140 || diastolic != null && diastolic >= 90 -> VitalTone(MedtrackColors.VitalCritical, MedtrackColors.VitalCriticalSoft)
                systolic != null && systolic >= 130 || diastolic != null && diastolic >= 80 -> VitalTone(MedtrackColors.VitalHigh, MedtrackColors.VitalHighSoft)
                else -> VitalTone(MedtrackColors.VitalOk, MedtrackColors.VitalOkSoft)
            }
        }
        "spo2" -> {
            val spo2 = value.firstNumber()
            when {
                spo2 != null && spo2 < 95f -> VitalTone(MedtrackColors.VitalCritical, MedtrackColors.VitalCriticalSoft)
                else -> VitalTone(MedtrackColors.VitalOk, MedtrackColors.VitalOkSoft)
            }
        }
        "hb" -> {
            val hb = value.firstNumber()
            when {
                hb != null && hb < 10f -> VitalTone(MedtrackColors.VitalCritical, MedtrackColors.VitalCriticalSoft)
                hb != null && hb < 11f -> VitalTone(MedtrackColors.VitalHigh, MedtrackColors.VitalHighSoft)
                else -> VitalTone(MedtrackColors.VitalOk, MedtrackColors.VitalOkSoft)
            }
        }
        else -> VitalTone(MedtrackColors.VitalOk, MedtrackColors.VitalOkSoft)
    }
}

private fun String.firstNumber(): Float? =
    Regex("""\d+(\.\d+)?""").find(this)?.value?.toFloatOrNull()

private fun PatientCase.matchesCaseSearch(query: String): Boolean {
    val needle = query.trim()
    if (needle.isBlank()) return true
    return listOfNotNull(
        patientName,
        uhid,
        phoneNumber,
        place,
        diagnosis,
        categoryLabel,
        subcategoryLabel,
    ).any { it.contains(needle, ignoreCase = true) }
}

private fun PatientCase.matchesCaseFilter(filter: String): Boolean =
    when (filter) {
        "red" -> isHighRisk
        "anc" -> category == CaseCategory.ANC || categoryLabel.contains("ANC", ignoreCase = true)
        "medicine" -> category == CaseCategory.MEDICINE || categoryLabel.contains("medicine", ignoreCase = true)
        "surgery" -> category == CaseCategory.SURGERY || categoryLabel.contains("surgery", ignoreCase = true)
        else -> true
    }

private fun PatientCase.riskReasonCount(): Int =
    highRiskReasons.count { it.isNotBlank() }.coerceAtLeast(1)

private fun PatientCase.dedupeKey(): String =
    uhid.takeIf { it.isNotBlank() }
        ?: listOfNotNull(patientName.lowercase(), age?.toString(), sexLabel?.lowercase()).joinToString("|")

private fun PatientCase.identityLine(): String =
    listOfNotNull(
        uhid,
        age?.let { "${it}y" },
        sexLabel,
        place,
    ).filter { it.isNotBlank() }.joinToString(" · ")

private fun PatientCase.caseListIdentityLine(): String =
    listOfNotNull(
        uhid.takeIf { it.isNotBlank() },
        sexLabel
            ?.trim()
            ?.takeIf { it.isNotBlank() }
            ?.let { if (it.length == 1) it.uppercase(Locale.getDefault()) else it.first().uppercaseChar().toString() },
        age?.toString(),
        place?.takeIf { it.isNotBlank() },
    ).joinToString(" \u00B7 ")

private fun String.initials(): String {
    val parts = trim().split(Regex("\\s+")).filter { it.isNotBlank() }
    return parts.take(2).joinToString("") { it.take(1).uppercase() }.ifBlank { "M" }
}

private fun CaseCategory.color(): Color =
    when (this) {
        CaseCategory.ANC -> MedtrackColors.Anc
        CaseCategory.SURGERY -> MedtrackColors.Surgery
        CaseCategory.MEDICINE -> MedtrackColors.Medicine
        CaseCategory.OTHER -> MedtrackColors.Primary
    }

private fun PatientCase.categoryColor(): Color =
    category.color()

private fun PatientCase.statusColor(): Color =
    when (status.name) {
        "ACTIVE" -> MedtrackColors.Success
        "COMPLETED" -> MedtrackColors.Primary
        "CANCELLED",
        "LOSS_TO_FOLLOW_UP" -> MedtrackColors.Muted
        else -> MedtrackColors.Primary
    }

private fun PatientTask.statusColor(): Color =
    when (status.uppercase()) {
        "OVERDUE" -> MedtrackColors.Danger
        "COMPLETED" -> MedtrackColors.Success
        "AWAITING_REPORTS" -> MedtrackColors.Warning
        "CANCELLED" -> MedtrackColors.Muted
        else -> MedtrackColors.Primary
    }

private fun PatientTask.isActionable(): Boolean =
    canComplete && status.uppercase() !in setOf("COMPLETED", "CANCELLED")

private enum class TaskGroup {
    OVERDUE,
    UPCOMING,
    DONE,
}

private fun PatientTask.taskGroup(): TaskGroup {
    val normalizedStatus = status.uppercase()
    return when {
        normalizedStatus in setOf("COMPLETED", "CANCELLED") -> TaskGroup.DONE
        normalizedStatus == "OVERDUE" || statusLabel.contains("overdue", ignoreCase = true) -> TaskGroup.OVERDUE
        !isActionable() -> TaskGroup.DONE
        else -> TaskGroup.UPCOMING
    }
}

private data class LatestVitalMetric(
    val label: String,
    val value: String,
    val unit: String,
)

private fun String.latestVitalPairs(): List<LatestVitalMetric> {
    val values = split("|")
        .map { it.trim() }
        .filter { it.isNotBlank() }
        .mapNotNull { metric ->
            val parts = metric.split(Regex("\\s+"), limit = 2)
            val label = parts.firstOrNull().orEmpty().trim()
            val value = parts.getOrNull(1).orEmpty().trim()
            label.takeIf { it.isNotBlank() }?.let { it to value.ifBlank { "\u2014" } }
        }
        .toMap()
    fun find(label: String, unit: String, vararg aliases: String): LatestVitalMetric {
        val value = aliases.firstNotNullOfOrNull { alias ->
            values.entries.firstOrNull { it.key.equals(alias, ignoreCase = true) }?.value
        } ?: "\u2014"
        return LatestVitalMetric(
            label = label,
            value = value,
            unit = if (value == "\u2014") "" else unit,
        )
    }
    return listOf(
        find("BP", "mmHg", "BP"),
        find("Pulse", "bpm", "PR", "Pulse"),
        find("SpO\u2082", "%", "SpO2", "SpO\u2082"),
        find("Hb", "g/dL", "Hb", "Hgb", "Hemoglobin"),
    )
}

private fun String.compactPatientName(): String =
    trim()
        .split(Regex("\\s+"))
        .filter { it.isNotBlank() }
        .take(2)
        .joinToString(" ")
        .ifBlank { this }

private fun VitalStatusResult.statusColor(): Color =
    when (status) {
        "green" -> MedtrackColors.Success
        "orange", "neutral" -> MedtrackColors.Warning
        "red" -> MedtrackColors.Danger
        else -> MedtrackColors.Muted
    }

data class VitalsEntryInput(
    val bpSystolic: Int?,
    val bpDiastolic: Int?,
    val pulse: Int?,
    val spo2: Int?,
    val weightKg: String?,
    val hemoglobin: String?,
)

@Composable
@OptIn(ExperimentalMaterial3Api::class)
private fun VitalsEntrySheet(
    patientCase: PatientCase?,
    thresholds: VitalsThresholdConfig?,
    onDismiss: () -> Unit,
    onSubmit: (VitalsEntryInput) -> Unit,
    existingVital: PatientVital? = null,
) {
    val editKey = existingVital?.id
    var systolic by remember(editKey) { mutableStateOf(existingVital?.bpSystolic?.toString() ?: "") }
    var diastolic by remember(editKey) { mutableStateOf(existingVital?.bpDiastolic?.toString() ?: "") }
    var pulse by remember(editKey) { mutableStateOf(existingVital?.pulse?.toString() ?: "") }
    var spo2 by remember(editKey) { mutableStateOf(existingVital?.spo2?.toString() ?: "") }
    var weight by remember(editKey) { mutableStateOf(existingVital?.weightKg.orEmpty()) }
    var hemoglobin by remember(editKey) { mutableStateOf(existingVital?.hemoglobin.orEmpty()) }
    val hasAnyMetric = listOf(systolic, diastolic, pulse, spo2, weight, hemoglobin).any { it.isNotBlank() }
    val hasPartialBloodPressure = systolic.isNotBlank() xor diastolic.isNotBlank()
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    ModalBottomSheet(
        sheetState = sheetState,
        onDismissRequest = onDismiss,
        containerColor = Color.White,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .imePadding()
                .navigationBarsPadding()
                .padding(start = 16.dp, end = 16.dp, bottom = 18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top,
            ) {
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(
                        text = if (existingVital != null) "Edit vitals" else "Add vitals",
                        color = MedtrackColors.Ink,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                }
                patientCase?.let {
                    Text(
                        text = "${it.patientName.compactPatientName()} · ${it.categoryLabel}",
                        modifier = Modifier.width(142.dp),
                        color = MedtrackColors.InkSoft,
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
            Text(
                text = if (thresholds == null) {
                    "Enter available measurements."
                } else {
                    "Normal - SBP < 140 / DBP < 90 - SpO2 >=95 - Hb >=11"
                },
                color = MedtrackColors.Muted,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            LazyColumn(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 356.dp),
                verticalArrangement = Arrangement.spacedBy(9.dp),
            ) {
                item {
                    Text(
                        text = "BLOOD PRESSURE",
                        color = MedtrackColors.Ink,
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.ExtraBold,
                    )
                    Spacer(modifier = Modifier.height(6.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                        VitalsNumberField(
                            value = systolic,
                            onValueChange = { systolic = it.filter(Char::isDigit) },
                            label = "SBP",
                            unit = "mmHg",
                            modifier = Modifier.weight(1f),
                        )
                        VitalsNumberField(
                            value = diastolic,
                            onValueChange = { diastolic = it.filter(Char::isDigit) },
                            label = "DBP",
                            unit = "mmHg",
                            modifier = Modifier.weight(1f),
                        )
                    }
                }
                item {
                    Text(
                        text = "OTHER VITALS",
                        color = MedtrackColors.Ink,
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.ExtraBold,
                    )
                    Spacer(modifier = Modifier.height(6.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                        VitalsNumberField(
                            value = pulse,
                            onValueChange = { pulse = it.filter(Char::isDigit) },
                            label = "Pulse",
                            unit = "bpm",
                            modifier = Modifier.weight(1f),
                        )
                        VitalsNumberField(
                            value = spo2,
                            onValueChange = { spo2 = it.filter(Char::isDigit) },
                            label = "SpO2",
                            unit = "%",
                            modifier = Modifier.weight(1f),
                        )
                    }
                }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                        VitalsNumberField(
                            value = weight,
                            onValueChange = { weight = it.filter { char -> char.isDigit() || char == '.' } },
                            label = "Weight",
                            unit = "kg",
                            modifier = Modifier.weight(1f),
                        )
                        VitalsNumberField(
                            value = hemoglobin,
                            onValueChange = { hemoglobin = it.filter { char -> char.isDigit() || char == '.' } },
                            label = "Hb",
                            unit = "g/dL",
                            modifier = Modifier.weight(1f),
                        )
                    }
                }
                if (hasPartialBloodPressure) {
                    item {
                        Text(text = "Enter both SBP and DBP.", color = MedtrackColors.Danger)
                    }
                }
                item {
                    VitalsThresholdFeedback(
                        thresholds = thresholds,
                        systolic = systolic.toIntOrNull(),
                        diastolic = diastolic.toIntOrNull(),
                        pulse = pulse.toDoubleOrNull(),
                        spo2 = spo2.toDoubleOrNull(),
                        weight = weight.toDoubleOrNull(),
                        hemoglobin = hemoglobin.toDoubleOrNull(),
                    )
                }
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = onDismiss, modifier = Modifier.weight(1f)) {
                    Text("Cancel")
                }
                Button(
                    onClick = {
                        onSubmit(
                            VitalsEntryInput(
                                bpSystolic = systolic.toIntOrNull(),
                                bpDiastolic = diastolic.toIntOrNull(),
                                pulse = pulse.toIntOrNull(),
                                spo2 = spo2.toIntOrNull(),
                                weightKg = weight.takeIf { it.isNotBlank() },
                                hemoglobin = hemoglobin.takeIf { it.isNotBlank() },
                            ),
                        )
                    },
                    enabled = hasAnyMetric && !hasPartialBloodPressure,
                    modifier = Modifier.weight(1f),
                ) {
                    Icon(Icons.Outlined.CheckCircle, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(modifier = Modifier.width(6.dp))
                    Text("Save vitals")
                }
            }
        }
    }
}

@Composable
private fun VitalsNumberField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    unit: String,
    modifier: Modifier = Modifier,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = {
            Text(
                text = label,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Bold,
            )
        },
        suffix = {
            Text(
                text = unit,
                color = MedtrackColors.Muted,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.SemiBold,
            )
        },
        modifier = modifier.height(72.dp),
        shape = RoundedCornerShape(12.dp),
        singleLine = true,
        textStyle = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.ExtraBold),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        colors = OutlinedTextFieldDefaults.colors(
            focusedContainerColor = Color.White,
            unfocusedContainerColor = Color.White,
            disabledContainerColor = Color.White,
        ),
    )
}
