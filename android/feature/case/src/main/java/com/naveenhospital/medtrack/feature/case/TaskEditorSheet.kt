package com.naveenhospital.medtrack.feature.cases

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.LockOpen
import androidx.compose.material.icons.outlined.StickyNote2
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.domain.model.FormChoice
import com.naveenhospital.medtrack.core.domain.model.NewTaskInput
import com.naveenhospital.medtrack.core.domain.model.PatientTask
import com.naveenhospital.medtrack.core.domain.model.TaskEditInput
import com.naveenhospital.medtrack.core.domain.model.TaskFormMetadata
import java.text.SimpleDateFormat
import java.util.Locale

private const val UNASSIGNED_VALUE = ""

sealed interface TaskSheetAction {
    data class Create(val input: NewTaskInput) : TaskSheetAction
    data class Edit(val input: TaskEditInput) : TaskSheetAction
    data class Note(val text: String) : TaskSheetAction
}

/**
 * Unified create / edit task sheet. Reuses the case-wizard field controls so it matches the
 * rest of the app. [onSubmit] performs the action and reports an error banner (or null on success,
 * which dismisses the sheet).
 */
@Composable
@OptIn(ExperimentalMaterial3Api::class)
fun TaskEditorSheet(
    metadata: TaskFormMetadata?,
    existingTask: PatientTask?,
    onDismiss: () -> Unit,
    onSubmit: (TaskSheetAction, (String?) -> Unit) -> Unit,
) {
    val isEdit = existingTask != null
    val isCompleted = existingTask?.status?.uppercase() == "COMPLETED"
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    val statusOptions = remember(metadata) { metadata?.statuses.orEmpty() }
    val typeOptions = remember(metadata) { metadata?.taskTypes.orEmpty() }
    val assigneeOptions = remember(metadata) {
        listOf(FormChoice(UNASSIGNED_VALUE, "Unassigned")) +
            metadata?.assignableUsers.orEmpty().map { FormChoice(it.id.toString(), it.name) }
    }

    var title by remember { mutableStateOf(existingTask?.title.orEmpty()) }
    var dueDate by remember { mutableStateOf(existingTask?.dueDate?.take(10) ?: todayIso()) }
    var status by remember {
        mutableStateOf(existingTask?.status ?: metadata?.defaultStatus ?: "SCHEDULED")
    }
    var taskType by remember {
        mutableStateOf(existingTask?.taskType ?: typeOptions.firstOrNull()?.value ?: "CUSTOM")
    }
    var assignee by remember { mutableStateOf(existingTask?.assignedUserId?.toString() ?: UNASSIGNED_VALUE) }
    var note by remember { mutableStateOf("") }
    var showNote by remember { mutableStateOf(false) }
    var banner by remember { mutableStateOf<String?>(null) }
    var submitting by remember { mutableStateOf(false) }

    fun assigneeId(): Long? = assignee.takeIf { it.isNotBlank() }?.toLongOrNull()

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
                .padding(start = 16.dp, end = 16.dp, bottom = 18.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(11.dp),
        ) {
            Text(
                text = if (isEdit) "Edit task" else "Add task",
                color = MedtrackColors.Ink,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.ExtraBold,
            )

            if (isCompleted && metadata?.canReopen == true) {
                ReopenRow(
                    enabled = !submitting,
                    onReopen = {
                        banner = null
                        submitting = true
                        onSubmit(TaskSheetAction.Edit(TaskEditInput(status = "SCHEDULED"))) { error ->
                            submitting = false
                            if (error != null) banner = error
                        }
                    },
                )
            }

            TextField("Title", title, required = true) { title = it }
            DateField("Due date", dueDate, required = true) { dueDate = it }
            FieldRow {
                DropdownField("Status", status, statusOptions, { status = it }, Modifier.weight(1f), required = true)
                DropdownField("Type", taskType, typeOptions, { taskType = it }, Modifier.weight(1f), required = true)
            }
            DropdownField("Assigned to", assignee, assigneeOptions, { assignee = it }, optional = true)

            if (isEdit) {
                NoteToggle(expanded = showNote, onToggle = { showNote = !showNote })
                if (showNote) {
                    MultilineField("Note for the timeline", note, optional = true) { note = it }
                    SecondaryButton(
                        label = "Save note",
                        enabled = note.isNotBlank() && !submitting,
                        onClick = {
                            banner = null
                            submitting = true
                            onSubmit(TaskSheetAction.Note(note.trim())) { error ->
                                submitting = false
                                if (error != null) banner = error else note = ""
                            }
                        },
                    )
                }
            }

            banner?.let { BannerError(it) }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = onDismiss, modifier = Modifier.weight(1f)) { Text("Cancel") }
                PrimaryButton(
                    label = if (isEdit) "Save changes" else "Add task",
                    submitting = submitting,
                    modifier = Modifier.weight(1.4f),
                    onClick = {
                        banner = null
                        when {
                            title.isBlank() -> banner = "Enter a task title."
                            dueDate.isBlank() -> banner = "Choose a due date."
                            else -> {
                                submitting = true
                                val action = if (isEdit) {
                                    TaskSheetAction.Edit(
                                        TaskEditInput(
                                            title = title.trim(),
                                            dueDate = dueDate,
                                            status = status,
                                            taskType = taskType,
                                            assignedUserId = assigneeId(),
                                            clearAssignee = assignee.isBlank(),
                                        ),
                                    )
                                } else {
                                    TaskSheetAction.Create(
                                        NewTaskInput(
                                            title = title.trim(),
                                            dueDate = dueDate,
                                            status = status,
                                            taskType = taskType,
                                            assignedUserId = assigneeId(),
                                        ),
                                    )
                                }
                                onSubmit(action) { error ->
                                    submitting = false
                                    if (error != null) banner = error
                                }
                            }
                        }
                    },
                )
            }
        }
    }
}

@Composable
private fun ReopenRow(enabled: Boolean, onReopen: () -> Unit) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(enabled = enabled, onClick = onReopen),
        shape = RoundedCornerShape(14.dp),
        color = MedtrackColors.WarningSoft,
        border = BorderStroke(1.dp, MedtrackColors.Warning.copy(alpha = 0.4f)),
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Outlined.LockOpen, contentDescription = null, tint = MedtrackColors.Warning, modifier = Modifier.size(20.dp))
            Column(Modifier.weight(1f)) {
                Text("Reopen task", color = MedtrackColors.Ink, fontWeight = FontWeight.Bold)
                Text(
                    "Move this completed task back to Scheduled.",
                    color = MedtrackColors.Muted,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun NoteToggle(expanded: Boolean, onToggle: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onToggle),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Outlined.StickyNote2, contentDescription = null, tint = MedtrackColors.Primary, modifier = Modifier.size(18.dp))
        Text(
            if (expanded) "Hide note" else "Add a note to the timeline",
            color = MedtrackColors.Primary,
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.ExtraBold,
        )
    }
}

@Composable
private fun PrimaryButton(label: String, submitting: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Surface(
        modifier = modifier
            .height(52.dp)
            .clickable(enabled = !submitting, onClick = onClick),
        shape = RoundedCornerShape(14.dp),
        color = MedtrackColors.Primary,
    ) {
        Box(contentAlignment = Alignment.Center) {
            if (submitting) {
                CircularProgressIndicator(color = Color.White, strokeWidth = 2.dp, modifier = Modifier.size(18.dp))
            } else {
                Text(label, color = Color.White, fontWeight = FontWeight.ExtraBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

@Composable
private fun SecondaryButton(label: String, enabled: Boolean, onClick: () -> Unit) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .height(46.dp)
            .clickable(enabled = enabled, onClick = onClick),
        shape = RoundedCornerShape(13.dp),
        color = if (enabled) MedtrackColors.PrimarySoft else MedtrackColors.SurfaceAlt,
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.Check, contentDescription = null, tint = if (enabled) MedtrackColors.Primary else MedtrackColors.Faint, modifier = Modifier.size(16.dp))
            Spacer(Modifier.width(6.dp))
            Text(label, color = if (enabled) MedtrackColors.Primary else MedtrackColors.Faint, fontWeight = FontWeight.ExtraBold)
        }
    }
}

private fun todayIso(): String =
    SimpleDateFormat("yyyy-MM-dd", Locale.US).format(java.util.Date())
