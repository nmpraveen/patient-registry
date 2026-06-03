package com.naveenhospital.medtrack.feature.calls

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.Phone
import androidx.compose.material.icons.outlined.PhoneInTalk
import androidx.compose.material.icons.outlined.PhoneMissed
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors

private data class OutcomeChoice(
    val value: String,
    val label: String,
    val icon: ImageVector,
    val color: Color,
)

private val outcomeChoices = listOf(
    OutcomeChoice("reached", "Reached", Icons.Outlined.CheckCircle, MedtrackColors.Success),
    OutcomeChoice("no-answer", "No answer", Icons.Outlined.PhoneMissed, MedtrackColors.Warning),
    OutcomeChoice("busy", "Busy", Icons.Outlined.PhoneInTalk, MedtrackColors.Primary),
    OutcomeChoice("wrong-number", "Wrong number", Icons.Outlined.ErrorOutline, MedtrackColors.Danger),
)

@Composable
@OptIn(ExperimentalMaterial3Api::class)
fun CallOutcomeSheet(
    patientName: String,
    onOutcome: (outcome: String, note: String?) -> Unit,
    onAttempted: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var selectedOutcome by rememberSaveable { mutableStateOf(outcomeChoices.first().value) }
    var note by rememberSaveable { mutableStateOf("") }

    ModalBottomSheet(
        sheetState = sheetState,
        onDismissRequest = onAttempted,
        containerColor = Color.White,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 16.dp, end = 16.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Surface(
                    shape = RoundedCornerShape(14.dp),
                    color = MedtrackColors.Primary.copy(alpha = 0.12f),
                    modifier = Modifier.size(44.dp),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            imageVector = Icons.Outlined.Phone,
                            contentDescription = null,
                            tint = MedtrackColors.Primary,
                            modifier = Modifier.size(22.dp),
                        )
                    }
                }
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(
                        text = "Call outcome",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = MedtrackColors.Ink,
                    )
                    Text(text = patientName, color = MedtrackColors.Muted, style = MaterialTheme.typography.bodySmall)
                }
            }

            // Two rows of two large, tappable outcome cards with colour-coded icons.
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                outcomeChoices.chunked(2).forEach { rowChoices ->
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                        rowChoices.forEach { choice ->
                            OutcomeCard(
                                choice = choice,
                                selected = selectedOutcome == choice.value,
                                onClick = { selectedOutcome = choice.value },
                                modifier = Modifier.weight(1f),
                            )
                        }
                    }
                }
            }

            OutlinedTextField(
                value = note,
                onValueChange = { note = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Short note (optional)") },
                minLines = 2,
            )

            Button(
                onClick = { onOutcome(selectedOutcome, note.trim().ifEmpty { null }) },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(50.dp),
            ) {
                Text("Save outcome", fontWeight = FontWeight.Bold)
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

@Composable
private fun OutcomeCard(
    choice: OutcomeChoice,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier
            .height(96.dp)
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(16.dp),
        color = if (selected) choice.color.copy(alpha = 0.12f) else MedtrackColors.Card,
        border = BorderStroke(
            width = if (selected) 2.dp else 1.dp,
            color = if (selected) choice.color else MedtrackColors.Border,
        ),
    ) {
        Column(
            modifier = Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = choice.color.copy(alpha = if (selected) 0.20f else 0.12f),
                modifier = Modifier.size(40.dp),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(
                        imageVector = choice.icon,
                        contentDescription = null,
                        tint = choice.color,
                        modifier = Modifier.size(24.dp),
                    )
                }
            }
            Text(
                text = choice.label,
                color = if (selected) MedtrackColors.Ink else MedtrackColors.InkSoft,
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 8.dp),
            )
        }
    }
}
