package com.naveenhospital.medtrack.feature.cases

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Chat
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.OpenInNew
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Favorite
import androidx.compose.material.icons.outlined.Phone
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.naveenhospital.medtrack.core.designsystem.MedtrackCard
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.designsystem.MedtrackCompactCard
import com.naveenhospital.medtrack.core.designsystem.MedtrackIconBadge
import com.naveenhospital.medtrack.core.designsystem.MedtrackMiniPill
import com.naveenhospital.medtrack.core.designsystem.MedtrackPage
import com.naveenhospital.medtrack.core.designsystem.MedtrackPullRefreshBox
import com.naveenhospital.medtrack.core.designsystem.MedtrackSectionTitle
import com.naveenhospital.medtrack.core.designsystem.MedtrackStatusPill
import com.naveenhospital.medtrack.core.domain.model.CaseCategory
import com.naveenhospital.medtrack.core.domain.model.PatientCase
import com.naveenhospital.medtrack.core.domain.model.PatientTask
import com.naveenhospital.medtrack.core.domain.model.PatientVital
import com.naveenhospital.medtrack.core.domain.model.VitalStatusResult
import com.naveenhospital.medtrack.core.domain.model.VitalsThresholdConfig

@Composable
fun CaseListScreen(
    cases: List<PatientCase>,
    isRefreshing: Boolean = false,
    error: String? = null,
    onRefresh: () -> Unit = {},
    onOpenCase: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .background(MedtrackColors.Surface)
            .padding(horizontal = 10.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    text = "Cases",
                    color = MedtrackColors.Ink,
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = "${cases.size} active records",
                    color = MedtrackColors.Muted,
                    style = MaterialTheme.typography.labelMedium,
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                MedtrackMiniPill(text = if (isRefreshing) "syncing" else "synced list", color = MedtrackColors.Primary)
                IconButton(onClick = onRefresh) {
                    Icon(imageVector = Icons.Outlined.Refresh, contentDescription = "Refresh cases")
                }
            }
        }
        error?.let { Text(text = it, color = MedtrackColors.Danger) }
        if (isRefreshing) {
            Text(text = "Refreshing", color = MedtrackColors.Muted)
        }
        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(8.dp),
            contentPadding = PaddingValues(bottom = 104.dp),
        ) {
            items(cases, key = { it.id }) { patientCase ->
                CaseRow(patientCase = patientCase, onClick = { onOpenCase(patientCase.id) })
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
) {
    var showVitalsDialog by rememberSaveable { mutableStateOf(false) }
    val listState = rememberLazyListState()

    Column(
        modifier = modifier
            .background(MedtrackColors.Surface)
            .padding(horizontal = 10.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(imageVector = Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back")
            }
            Text(
                text = patientCase?.patientName ?: "Case $caseId",
                color = MedtrackColors.Ink,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            IconButton(onClick = onRefresh) {
                Icon(imageVector = Icons.Outlined.Refresh, contentDescription = "Refresh")
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
                verticalArrangement = Arrangement.spacedBy(8.dp),
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
                    item {
                        MedtrackSectionTitle(
                            title = "Tasks",
                            trailing = "${tasks.count { it.isActionable() }} open",
                        )
                    }
                    item {
                        MedtrackCompactCard {
                            if (tasks.isEmpty()) {
                                Text(text = "No tasks recorded", color = MedtrackColors.Muted)
                            } else {
                                tasks.forEach { task ->
                                    TaskRow(task = task, onCompleteTask = onCompleteTask)
                                }
                            }
                        }
                    }
                    item {
                        MedtrackSectionTitle(
                            title = "Vitals",
                            trailing = "${vitals.size} records",
                        )
                    }
                    item {
                        MedtrackCompactCard {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Text("Vitals history", fontWeight = FontWeight.Bold, color = MedtrackColors.Ink)
                                Button(
                                    onClick = { showVitalsDialog = true },
                                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
                                    modifier = Modifier.height(36.dp),
                                ) {
                                    Icon(imageVector = Icons.Outlined.Add, contentDescription = null, modifier = Modifier.size(16.dp))
                                    Spacer(modifier = Modifier.width(4.dp))
                                    Text("Add")
                                }
                            }
                            if (vitals.isEmpty()) {
                                Text(text = patientCase.latestVitalSummary ?: "No vitals recorded", color = MedtrackColors.Muted)
                            } else {
                                vitals.forEach { vital ->
                                    VitalsRow(vital = vital)
                                }
                            }
                        }
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
        VitalsEntrySheet(
            thresholds = vitalsThresholds,
            onDismiss = { showVitalsDialog = false },
            onSubmit = { input ->
                showVitalsDialog = false
                onAddVitals(input)
            },
        )
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun CaseHero(
    patientCase: PatientCase,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        color = Color.Transparent,
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(
                    Brush.linearGradient(
                        listOf(MedtrackColors.PrimaryDark, MedtrackColors.Primary),
                    ),
                )
                .padding(15.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.Top,
                ) {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Surface(shape = RoundedCornerShape(16.dp), color = Color.White.copy(alpha = 0.16f), modifier = Modifier.size(52.dp)) {
                            Box(contentAlignment = Alignment.Center) {
                                Text(
                                    text = patientCase.patientName.initials(),
                                    color = Color.White,
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.Bold,
                                )
                            }
                        }
                        Column(verticalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.weight(1f)) {
                            Text(
                                text = patientCase.patientName,
                                color = Color.White,
                                style = MaterialTheme.typography.titleLarge,
                                fontWeight = FontWeight.Bold,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                            Text(
                                text = patientCase.identityLine(),
                                color = Color.White.copy(alpha = 0.78f),
                                style = MaterialTheme.typography.bodySmall,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                    }
                    if (patientCase.isHighRisk) {
                        Surface(
                            shape = RoundedCornerShape(50),
                            color = MedtrackColors.DangerSoft,
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(4.dp),
                            ) {
                                Icon(imageVector = Icons.Outlined.Favorite, contentDescription = null, tint = MedtrackColors.Danger, modifier = Modifier.size(14.dp))
                                Text("Red", color = MedtrackColors.Danger, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }

                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    HeroPill(patientCase.uhid)
                    HeroPill(patientCase.categoryLabel)
                    patientCase.subcategoryLabel?.takeIf { it.isNotBlank() }?.let { HeroPill(it) }
                    HeroPill(patientCase.status.label)
                }

                Text(
                    text = patientCase.diagnosis.ifBlank { "Case details" },
                    color = Color.White,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun HeroPill(text: String) {
    Surface(shape = RoundedCornerShape(50), color = Color.White.copy(alpha = 0.16f)) {
        Text(
            text = text,
            color = Color.White,
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
        shape = RoundedCornerShape(22.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border),
        shadowElevation = 10.dp,
    ) {
        Row(
            modifier = Modifier.padding(8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Button(
                onClick = onCallPatient,
                enabled = !patientCase.phoneNumber.isNullOrBlank(),
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Success),
            ) {
                Icon(imageVector = Icons.Outlined.Phone, contentDescription = null, modifier = Modifier.size(16.dp))
                Spacer(modifier = Modifier.width(5.dp))
                Text("Call")
            }
            Button(
                onClick = onMessagePatient,
                enabled = !patientCase.phoneNumber.isNullOrBlank(),
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.SuccessSoft, contentColor = MedtrackColors.Success),
            ) {
                Icon(imageVector = Icons.AutoMirrored.Outlined.Chat, contentDescription = null, modifier = Modifier.size(16.dp))
                Spacer(modifier = Modifier.width(5.dp))
                Text("WhatsApp")
            }
            Button(
                onClick = onAddVitals,
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Ink),
            ) {
                Icon(imageVector = Icons.Outlined.Add, contentDescription = null, modifier = Modifier.size(16.dp))
                Spacer(modifier = Modifier.width(5.dp))
                Text("Vitals")
            }
        }
    }
}

@Composable
private fun TaskRow(
    task: PatientTask,
    onCompleteTask: (PatientTask) -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(13.dp),
        color = MedtrackColors.Surface,
        border = BorderStroke(1.dp, MedtrackColors.Border.copy(alpha = 0.55f)),
    ) {
        Row(
            modifier = Modifier.padding(9.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            MedtrackIconBadge(icon = Icons.Outlined.CalendarMonth, tint = task.statusColor(), modifier = Modifier.size(34.dp))
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    text = task.title,
                    color = MedtrackColors.Ink,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = task.dueDate ?: "No due date",
                    color = MedtrackColors.Muted,
                    style = MaterialTheme.typography.labelMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            MedtrackMiniPill(text = task.statusLabel, color = task.statusColor())
            if (task.isActionable()) {
                Button(
                    onClick = { onCompleteTask(task) },
                    modifier = Modifier.height(34.dp),
                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 5.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Ink),
                ) {
                    Icon(imageVector = Icons.Outlined.CheckCircle, contentDescription = null, modifier = Modifier.size(15.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Done")
                }
            }
        }
    }
}

@Composable
private fun VitalsRow(vital: PatientVital) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        color = MedtrackColors.Surface,
        border = BorderStroke(1.dp, MedtrackColors.Border.copy(alpha = 0.5f)),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    text = vital.summary.ifBlank { "Vitals recorded" },
                    color = MedtrackColors.Ink,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(text = vital.recordedAt.take(10), color = MedtrackColors.Muted, style = MaterialTheme.typography.labelSmall)
            }
            MedtrackIconBadge(icon = Icons.Outlined.Favorite, tint = MedtrackColors.Danger, modifier = Modifier.size(34.dp))
        }
    }
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
            MedtrackStatusPill(
                text = "$label ${result.label}",
                color = result.statusColor(),
            )
        }
    }
}

@Composable
private fun CaseRow(
    patientCase: PatientCase,
    onClick: () -> Unit,
) {
    MedtrackCompactCard(
        modifier = Modifier.clickable(onClick = onClick),
        borderColor = if (patientCase.isHighRisk) MedtrackColors.Danger.copy(alpha = 0.45f) else MedtrackColors.Border,
    ) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(9.dp),
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth(),
        ) {
            MedtrackIconBadge(icon = Icons.AutoMirrored.Outlined.OpenInNew, tint = patientCase.categoryColor(), modifier = Modifier.size(36.dp))
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    text = patientCase.patientName,
                    color = MedtrackColors.Ink,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = patientCase.identityLine(),
                    color = MedtrackColors.Muted,
                    style = MaterialTheme.typography.labelMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            MedtrackMiniPill(text = patientCase.categoryLabel, color = patientCase.categoryColor())
        }
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
            patientCase.nextTaskDueDate?.let {
                MedtrackMiniPill(text = it.take(10), color = MedtrackColors.Primary)
            }
            if (patientCase.isHighRisk) {
                MedtrackMiniPill(text = "Red flag", color = MedtrackColors.Danger)
            }
        }
        Text(
            text = patientCase.diagnosis,
            color = MedtrackColors.Muted,
            style = MaterialTheme.typography.bodySmall,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

private fun PatientCase.identityLine(): String =
    listOfNotNull(
        uhid,
        age?.let { "${it}y" },
        sexLabel,
        place,
    ).filter { it.isNotBlank() }.joinToString(" - ")

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
    if (categoryLabel.trim().replace("-", " ").contains("rehab", ignoreCase = true)) {
        MedtrackColors.CustomRehab
    } else {
        category.color()
    }

private fun PatientTask.statusColor(): Color =
    when (status.uppercase()) {
        "COMPLETED" -> MedtrackColors.Success
        "AWAITING_REPORTS" -> MedtrackColors.Warning
        "CANCELLED" -> MedtrackColors.Muted
        else -> MedtrackColors.Primary
    }

private fun PatientTask.isActionable(): Boolean =
    canComplete && status.uppercase() !in setOf("COMPLETED", "CANCELLED")

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
    thresholds: VitalsThresholdConfig?,
    onDismiss: () -> Unit,
    onSubmit: (VitalsEntryInput) -> Unit,
) {
    var systolic by rememberSaveable { mutableStateOf("") }
    var diastolic by rememberSaveable { mutableStateOf("") }
    var pulse by rememberSaveable { mutableStateOf("") }
    var spo2 by rememberSaveable { mutableStateOf("") }
    var weight by rememberSaveable { mutableStateOf("") }
    var hemoglobin by rememberSaveable { mutableStateOf("") }
    val hasAnyMetric = listOf(systolic, diastolic, pulse, spo2, weight, hemoglobin).any { it.isNotBlank() }
    val hasPartialBloodPressure = systolic.isNotBlank() xor diastolic.isNotBlank()
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    ModalBottomSheet(
        sheetState = sheetState,
        onDismissRequest = onDismiss,
        containerColor = MedtrackColors.Surface,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .imePadding()
                .navigationBarsPadding()
                .padding(start = 16.dp, end = 16.dp, bottom = 22.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = "Add vitals",
                color = MedtrackColors.Ink,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
            LazyColumn(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 420.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                        OutlinedTextField(
                            value = systolic,
                            onValueChange = { systolic = it.filter(Char::isDigit) },
                            label = { Text("SBP") },
                            modifier = Modifier.weight(1f),
                            singleLine = true,
                        )
                        OutlinedTextField(
                            value = diastolic,
                            onValueChange = { diastolic = it.filter(Char::isDigit) },
                            label = { Text("DBP") },
                            modifier = Modifier.weight(1f),
                            singleLine = true,
                        )
                    }
                }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                        OutlinedTextField(
                            value = pulse,
                            onValueChange = { pulse = it.filter(Char::isDigit) },
                            label = { Text("Pulse") },
                            modifier = Modifier.weight(1f),
                            singleLine = true,
                        )
                        OutlinedTextField(
                            value = spo2,
                            onValueChange = { spo2 = it.filter(Char::isDigit) },
                            label = { Text("SpO2") },
                            modifier = Modifier.weight(1f),
                            singleLine = true,
                        )
                    }
                }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                        OutlinedTextField(
                            value = weight,
                            onValueChange = { weight = it.filter { char -> char.isDigit() || char == '.' } },
                            label = { Text("Weight") },
                            modifier = Modifier.weight(1f),
                            singleLine = true,
                        )
                        OutlinedTextField(
                            value = hemoglobin,
                            onValueChange = { hemoglobin = it.filter { char -> char.isDigit() || char == '.' } },
                            label = { Text("Hgb") },
                            modifier = Modifier.weight(1f),
                            singleLine = true,
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
                    Text("Save")
                }
            }
        }
    }
}
