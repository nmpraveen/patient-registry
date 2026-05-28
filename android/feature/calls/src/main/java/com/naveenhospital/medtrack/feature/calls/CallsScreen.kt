package com.naveenhospital.medtrack.feature.calls

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Chat
import androidx.compose.material.icons.automirrored.outlined.OpenInNew
import androidx.compose.material.icons.outlined.FilterList
import androidx.compose.material.icons.outlined.Phone
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.designsystem.MedtrackCompactCard
import com.naveenhospital.medtrack.core.designsystem.MedtrackIconBadge
import com.naveenhospital.medtrack.core.designsystem.MedtrackMiniPill
import com.naveenhospital.medtrack.core.designsystem.MedtrackSectionTitle
import com.naveenhospital.medtrack.core.domain.model.PatientCase
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun CallsScreen(
    cases: List<PatientCase>,
    callerName: String,
    isRefreshing: Boolean,
    error: String?,
    actionMessage: String?,
    onRefresh: () -> Unit,
    onOpenCase: (String) -> Unit,
    onCallPatient: (PatientCase) -> Unit,
    onMessagePatient: (PatientCase) -> Unit,
    modifier: Modifier = Modifier,
) {
    var filter by rememberSaveable { mutableStateOf("today") }
    val callableCases = cases
        .filter { !it.phoneNumber.isNullOrBlank() }
        .sortedWith(compareByDescending<PatientCase> { it.isHighRisk }.thenBy { it.nextTaskDueDate ?: "" })
    val todayToken = todayToken()
    val visibleCases = when (filter) {
        "red" -> callableCases.filter { it.isHighRisk }
        "all" -> callableCases
        else -> callableCases.filter { it.nextTaskDueDate?.contains(todayToken) == true }
            .ifEmpty { callableCases.take(8) }
    }
    val upNext = visibleCases.firstOrNull()
    val priorityCount = callableCases.count { it.isHighRisk }
    val remainingCount = visibleCases.size
    val totalCount = callableCases.size
    val remainingProgress = if (totalCount == 0) 0f else remainingCount.toFloat() / totalCount.toFloat()

    Column(
        modifier = modifier
            .fillMaxSize()
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
                Text("Call queue", color = MedtrackColors.Ink, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                Text("${callableCases.size} callable cases", color = MedtrackColors.Muted, style = MaterialTheme.typography.labelMedium)
            }
            IconButton(onClick = onRefresh) {
                Icon(imageVector = Icons.Outlined.Refresh, contentDescription = "Refresh")
            }
        }

        error?.let { Text(text = it, color = MedtrackColors.Danger) }
        actionMessage?.let { Text(text = it, color = MedtrackColors.Muted) }
        if (isRefreshing) {
            Text(text = "Refreshing", color = MedtrackColors.Muted)
        }

        CallQueueHero(
            upNext = upNext,
            callerName = callerName,
            remainingCount = remainingCount,
            totalCount = totalCount,
            redCount = priorityCount,
            progress = remainingProgress,
            onOpenCase = onOpenCase,
            onCallPatient = onCallPatient,
        )

        Row(horizontalArrangement = Arrangement.spacedBy(7.dp), modifier = Modifier.fillMaxWidth()) {
            QueueFilterChip("Today", filter == "today", { filter = "today" })
            QueueFilterChip("Red", filter == "red", { filter = "red" })
            QueueFilterChip("All", filter == "all", { filter = "all" })
        }

        MedtrackSectionTitle(title = "Next calls", trailing = "${visibleCases.size} shown")

        if (visibleCases.isEmpty() && !isRefreshing) {
            MedtrackCompactCard {
                Text(text = "No callable patients", color = MedtrackColors.Muted)
            }
        } else {
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = PaddingValues(bottom = 104.dp),
            ) {
                items(visibleCases, key = { it.id }) { patientCase ->
                    CallQueueRow(
                        patientCase = patientCase,
                        onOpenCase = { onOpenCase(patientCase.id) },
                        onCallPatient = { onCallPatient(patientCase) },
                        onMessagePatient = { onMessagePatient(patientCase) },
                    )
                }
            }
        }
    }
}

@Composable
private fun CallQueueHero(
    upNext: PatientCase?,
    callerName: String,
    remainingCount: Int,
    totalCount: Int,
    redCount: Int,
    progress: Float,
    onOpenCase: (String) -> Unit,
    onCallPatient: (PatientCase) -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border),
        shadowElevation = 2.dp,
    ) {
        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(verticalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Caller - $callerName",
                        color = MedtrackColors.Muted,
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text("Up next", color = MedtrackColors.Primary, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
                    Text(
                        text = upNext?.patientName ?: "No call selected",
                        color = MedtrackColors.Ink,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = upNext?.nextTaskTitle ?: "Refresh or adjust filters",
                        color = MedtrackColors.Muted,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Box(contentAlignment = Alignment.Center, modifier = Modifier.size(78.dp)) {
                    CircularProgressIndicator(
                        progress = { progress.coerceIn(0f, 1f) },
                        modifier = Modifier.size(70.dp),
                        color = MedtrackColors.Primary,
                        trackColor = MedtrackColors.SurfaceAlt,
                        strokeWidth = 7.dp,
                    )
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(remainingCount.toString(), color = MedtrackColors.Ink, fontWeight = FontWeight.Bold)
                        Text("left", color = MedtrackColors.Muted, style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(7.dp), modifier = Modifier.fillMaxWidth()) {
                MedtrackMiniPill(text = "$remainingCount of $totalCount left", color = MedtrackColors.Primary)
                MedtrackMiniPill(text = "~${remainingCount * 3} min left", color = MedtrackColors.Warning)
                if (redCount > 0) {
                    MedtrackMiniPill(text = "$redCount red", color = MedtrackColors.Danger)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                Button(
                    onClick = { upNext?.let(onCallPatient) },
                    enabled = upNext != null,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Success),
                ) {
                    Icon(imageVector = Icons.Outlined.Phone, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(5.dp))
                    Text("Call now")
                }
                Button(
                    onClick = { upNext?.let { onOpenCase(it.id) } },
                    enabled = upNext != null,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Ink),
                ) {
                    Icon(imageVector = Icons.AutoMirrored.Outlined.OpenInNew, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(5.dp))
                    Text("Open")
                }
            }
        }
    }
}

@Composable
private fun QueueFilterChip(label: String, selected: Boolean, onClick: () -> Unit) {
    FilterChip(
        selected = selected,
        onClick = onClick,
        label = { Text(label, fontWeight = FontWeight.SemiBold) },
        leadingIcon = if (selected) {
            { Icon(imageVector = Icons.Outlined.FilterList, contentDescription = null, modifier = Modifier.size(15.dp)) }
        } else {
            null
        },
        colors = FilterChipDefaults.filterChipColors(
            selectedContainerColor = MedtrackColors.Primary,
            selectedLabelColor = Color.White,
            selectedLeadingIconColor = Color.White,
            containerColor = MedtrackColors.Card,
            labelColor = MedtrackColors.Ink,
        ),
        border = FilterChipDefaults.filterChipBorder(
            enabled = true,
            selected = selected,
            borderColor = MedtrackColors.Border,
            selectedBorderColor = MedtrackColors.Primary,
        ),
    )
}

@Composable
private fun CallQueueRow(
    patientCase: PatientCase,
    onOpenCase: () -> Unit,
    onCallPatient: () -> Unit,
    onMessagePatient: () -> Unit,
) {
    MedtrackCompactCard(
        modifier = Modifier.clickable(onClick = onOpenCase),
        borderColor = if (patientCase.isHighRisk) MedtrackColors.Danger.copy(alpha = 0.45f) else MedtrackColors.Border,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(9.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            MedtrackIconBadge(icon = Icons.Outlined.Phone, tint = if (patientCase.isHighRisk) MedtrackColors.Danger else MedtrackColors.Primary)
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(patientCase.patientName, color = MedtrackColors.Ink, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(patientCase.identityLine(), color = MedtrackColors.Muted, style = MaterialTheme.typography.labelMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            patientCase.nextTaskDueDate?.takeIf { it.isNotBlank() }?.let {
                MedtrackMiniPill(text = it.take(10), color = if (patientCase.isHighRisk) MedtrackColors.Danger else MedtrackColors.Primary)
            }
        }
        Text(
            text = patientCase.nextTaskTitle ?: patientCase.diagnosis,
            color = MedtrackColors.Muted,
            style = MaterialTheme.typography.bodySmall,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            Button(
                onClick = onCallPatient,
                modifier = Modifier.weight(1f).height(38.dp),
                contentPadding = PaddingValues(horizontal = 8.dp),
                colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Success),
            ) {
                Icon(imageVector = Icons.Outlined.Phone, contentDescription = null, modifier = Modifier.size(15.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text("Call")
            }
            Button(
                onClick = onMessagePatient,
                modifier = Modifier.weight(1f).height(38.dp),
                contentPadding = PaddingValues(horizontal = 8.dp),
                colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.SuccessSoft, contentColor = MedtrackColors.Success),
            ) {
                Icon(imageVector = Icons.AutoMirrored.Outlined.Chat, contentDescription = null, modifier = Modifier.size(15.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text("WhatsApp")
            }
        }
    }
}

private fun PatientCase.identityLine(): String =
    listOfNotNull(uhid, age?.let { "${it}y" }, sexLabel, place).filter { it.isNotBlank() }.joinToString(" - ")

private fun todayToken(): String =
    SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())
