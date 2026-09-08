package com.naveenhospital.medtrack.feature.cases

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.domain.model.RelatedCase
import com.naveenhospital.medtrack.core.domain.model.RelatedCasePage
import kotlinx.coroutines.CancellationException

internal data class RelatedCasesState(
    val cases: List<RelatedCase>, val loading: Boolean, val error: String?,
    val hasMore: Boolean, val more: () -> Unit, val retry: () -> Unit,
)
@Composable
internal fun rememberRelatedCases(caseId: String, revision: Int, load: suspend (String?) -> RelatedCasePage): RelatedCasesState {
    val loader by rememberUpdatedState(load)
    var rows by remember(caseId, revision) { mutableStateOf<List<RelatedCase>>(emptyList()) }
    var cursor by remember(caseId, revision) { mutableStateOf<String?>(null) }
    var nextCursor by remember(caseId, revision) { mutableStateOf<String?>(null) }
    var loading by remember(caseId, revision) { mutableStateOf(true) }
    var error by remember(caseId, revision) { mutableStateOf<String?>(null) }
    var retry by remember(caseId, revision) { mutableStateOf(0) }
    LaunchedEffect(caseId, revision, cursor, retry) {
        loading = true
        error = null
        try {
            val page = loader(cursor)
            rows = ((if (cursor == null) emptyList() else rows) + page.results).distinctBy { it.id }
            nextCursor = page.nextCursor
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { error = failure.message ?: "Unable to load patient cases" }
        finally { loading = false }
    }
    return RelatedCasesState(rows, loading, error, nextCursor != null,
        more = { if (!loading) cursor = nextCursor }, retry = { retry += 1 })
}
@Composable
internal fun RelatedCaseSelector(caseId: String, state: RelatedCasesState, onSelect: (String) -> Unit) {
    var expanded by remember(caseId) { mutableStateOf(false) }
    Column {
        if (state.error != null) {
            Text("Patient cases unavailable", color = MedtrackColors.Muted)
            TextButton(onClick = state.retry) { Text("Retry cases") }
        } else if (state.cases.size > 1 || state.hasMore) {
            TextButton(onClick = { expanded = true }) { Text("Patient cases (${state.cases.size}${if (state.hasMore) "+" else ""})") }
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                state.cases.forEach { related ->
                    DropdownMenuItem(
                        text = { Column {
                            Text(related.department + if (related.id.toString() == caseId) " · Selected" else "")
                            Text(related.diagnosis)
                            Text(related.status, color = MedtrackColors.Muted)
                        } },
                        onClick = { expanded = false; if (related.id.toString() != caseId) onSelect(related.id.toString()) },
                    )
                }
                if (state.hasMore) DropdownMenuItem(text = { Text(if (state.loading) "Loading…" else "Load more cases") },
                    enabled = !state.loading, onClick = state.more)
            }
        }
    }
}
