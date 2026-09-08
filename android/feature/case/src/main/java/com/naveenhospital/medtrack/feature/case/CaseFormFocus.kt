package com.naveenhospital.medtrack.feature.cases

import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics

internal val LocalCaseFocus = staticCompositionLocalOf<Pair<String, Int>?> { null }

@Composable
internal fun formFocusModifier(label: String): Modifier {
    val requester = remember { FocusRequester() }
    val bringIntoView = remember { BringIntoViewRequester() }
    val requested = LocalCaseFocus.current
    LaunchedEffect(requested) {
        if (requested?.first == label) {
            requester.requestFocus()
            bringIntoView.bringIntoView()
        }
    }
    return Modifier.bringIntoViewRequester(bringIntoView).focusRequester(requester).semantics { contentDescription = label }
}
internal val serverFieldLabels = mapOf(
    "first_name" to "First name", "last_name" to "Last name", "prefix" to "Prefix",
    "gender" to "Sex", "age" to "Age", "phone_number" to "Phone", "uhid" to "UHID (optional)",
    "selected_patient_id" to "Existing patient", "category" to "Department", "subcategory" to "Subcategory",
    "diagnosis" to "Diagnosis / reason", "blood_group" to "Blood group", "place" to "Place / district",
    "referred_by" to "Referred by", "notes" to "Notes", "lmp" to "LMP", "edd" to "EDD", "usg_edd" to "USG EDD",
    "rch_number" to "RCH number", "surgical_pathway" to "Pathway", "surgery_date" to "Surgery date",
    "review_date" to "Review date", "review_frequency" to "Review frequency",
)
internal fun validationFocusLabel(message: String): String? = when {
    "first name" in message -> "First name"
    "last name" in message -> "Last name"
    "prefix" in message -> "Prefix"
    "sex" in message -> "Sex"
    "age" in message -> "Age"
    "phone" in message -> "Phone"
    "existing patient" in message -> "Existing patient"
    "subcategory" in message -> "Subcategory"
    "category" in message -> "Department"
    "diagnosis" in message -> "Diagnosis / reason"
    "EDD" in message -> "EDD"
    "LMP" in message -> "LMP"
    "RCH" in message -> "RCH number"
    "surgical pathway" in message -> "Pathway"
    "surgery date" in message -> "Surgery date"
    "review date" in message -> "Review date"
    else -> null
}
