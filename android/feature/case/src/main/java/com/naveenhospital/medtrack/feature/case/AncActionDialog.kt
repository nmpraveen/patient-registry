package com.naveenhospital.medtrack.feature.cases

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.naveenhospital.medtrack.core.domain.model.PatientCase
import com.naveenhospital.medtrack.core.domain.model.PatientTask
import java.util.UUID

@Composable
internal fun AncActionDialog(
    patientCase: PatientCase,
    tasks: List<PatientTask>,
    canEditTask: Boolean,
    onSubmit: (Map<String, Any>, (String?) -> Unit) -> Unit,
    onDismiss: () -> Unit,
) {
    var action by remember { mutableStateOf("outcome") }
    var outcome by remember { mutableStateOf("") }
    var date by remember { mutableStateOf("") }
    var edd by remember { mutableStateOf("") }
    var reason by remember { mutableStateOf("") }
    var destination by remember { mutableStateOf("") }
    var followUp by remember { mutableStateOf("") }
    var selected by remember { mutableStateOf(setOf<String>()) }
    var saving by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val payload = buildMap<String, Any> {
        put("action", action)
        put("base_updated_at", patientCase.serverUpdatedAt)
        put("reason", reason.trim())
        put("task_policy", if (selected.isEmpty() || action == "correct_edd") "retain" else "cancel_selected")
        if (action == "correct_edd") put("usg_edd", edd) else {
            put("outcome", outcome); put("outcome_date", date)
            put("referral_destination", destination.trim()); put("continue_follow_up", followUp)
            put("cancel_task_ids", selected.map { it.toLong() })
        }
    }
    // Keep the same identifier for retries of an unchanged submission.
    val writeId = remember(payload) { "anc-${UUID.randomUUID()}" }
    AlertDialog(
        onDismissRequest = { if (!saving) onDismiss() },
        title = { Text("ANC outcome / EDD correction") },
        text = {
            Column(Modifier.heightIn(max = 500.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("${patientCase.patientName} · ${patientCase.categoryLabel} · Case ${patientCase.id}")
                listOf("outcome" to "Record outcome", "correct_edd" to "Correct USG EDD").forEach { (value, label) ->
                    Row { RadioButton(action == value, { action = value }, enabled = !saving); Text(label) }
                }
                if (action == "correct_edd") {
                    OutlinedTextField(edd, { edd = it }, label = { Text("USG EDD (YYYY-MM-DD)") }, enabled = !saving, modifier = Modifier.fillMaxWidth())
                    Text("All task dates and statuses will be retained.")
                } else {
                    listOf("delivery" to "Delivery", "loss_to_follow_up" to "Loss to follow-up", "referral" to "Referral", "other" to "Other resolution").forEach { (value, label) ->
                        Row { RadioButton(outcome == value, { outcome = value }, enabled = !saving); Text(label) }
                    }
                    OutlinedTextField(date, { date = it }, label = { Text("Outcome date (YYYY-MM-DD)") }, enabled = !saving, modifier = Modifier.fillMaxWidth())
                    if (outcome == "referral") OutlinedTextField(destination, { destination = it }, label = { Text("Referral destination") }, enabled = !saving, modifier = Modifier.fillMaxWidth())
                    listOf("continue" to "Continue follow-up", "close" to "Close this case").forEach { (value, label) ->
                        Row { RadioButton(followUp == value, { followUp = value }, enabled = !saving); Text(label) }
                    }
                    Text("Open tasks: retain all unless selected for cancellation.")
                    tasks.filter { it.status in setOf("SCHEDULED", "AWAITING_REPORTS") }.forEach { task ->
                        Row {
                            Checkbox(task.id in selected, { checked -> selected = if (checked) selected + task.id else selected - task.id }, enabled = canEditTask && !saving)
                            Text("${task.title} · ${task.dueDate} · ${task.statusLabel}")
                        }
                    }
                }
                OutlinedTextField(reason, { reason = it }, label = { Text("Reason") }, enabled = !saving, modifier = Modifier.fillMaxWidth())
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            TextButton(enabled = !saving && reason.isNotBlank() &&
                (if (action == "correct_edd") edd.isNotBlank() else outcome.isNotBlank() && date.isNotBlank() && followUp.isNotBlank() && (outcome != "referral" || destination.isNotBlank())),
                onClick = {
                    saving = true
                    onSubmit(payload + ("client_write_id" to writeId)) { message ->
                        saving = false; error = message
                        if (message == null) onDismiss()
                    }
                }) { Text(if (saving) "Saving…" else "Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !saving) { Text("Cancel") } },
    )
}
