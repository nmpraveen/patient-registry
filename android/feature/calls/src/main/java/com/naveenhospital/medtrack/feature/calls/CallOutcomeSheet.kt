package com.naveenhospital.medtrack.feature.calls

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors

private val outcomeChoices = listOf(
    "reached" to "Reached",
    "no-answer" to "No answer",
    "busy" to "Busy",
    "wrong-number" to "Wrong number",
)

@Composable
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
fun CallOutcomeSheet(
    patientName: String,
    onOutcome: (outcome: String, note: String?) -> Unit,
    onAttempted: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var selectedOutcome by rememberSaveable { mutableStateOf(outcomeChoices.first().first) }
    var note by rememberSaveable { mutableStateOf("") }

    ModalBottomSheet(
        sheetState = sheetState,
        onDismissRequest = onAttempted,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 16.dp, end = 16.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = "Call outcome",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Text(text = patientName, color = MedtrackColors.Muted)

            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                outcomeChoices.forEach { (outcome, label) ->
                    FilterChip(
                        selected = selectedOutcome == outcome,
                        onClick = { selectedOutcome = outcome },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = MedtrackColors.Primary,
                            selectedLabelColor = Color.White,
                            containerColor = MedtrackColors.Card,
                            labelColor = MedtrackColors.Ink,
                        ),
                        label = { Text(label) },
                    )
                }
            }

            OutlinedTextField(
                value = note,
                onValueChange = { note = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Short note") },
                minLines = 2,
            )

            Button(
                onClick = { onOutcome(selectedOutcome, note.trim().ifEmpty { null }) },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Save outcome")
            }

            TextButton(
                onClick = onAttempted,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("No outcome")
            }
        }
    }
}
