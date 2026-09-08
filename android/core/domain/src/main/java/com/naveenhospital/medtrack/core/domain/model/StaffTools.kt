package com.naveenhospital.medtrack.core.domain.model

/** Operational records are independent of clinical cases and tasks. */
data class DirectoryPhone(val label: String, val number: String, val extension: String)

data class DirectoryContact(
    val id: Long,
    val name: String,
    val role: String,
    val organisation: String,
    val notes: String,
    val phones: List<DirectoryPhone>,
    val favourite: Boolean,
)

data class StaffAnnouncement(
    val id: Long,
    val title: String,
    val text: String,
    val priority: String,
    val publisher: String,
    val startsAt: String,
    val endsAt: String,
)

/** Numeric phone only. The extension stays visible for manual entry in the dialer. */
fun DirectoryPhone.dialNumber(): String? = number.trim()
    .takeIf { it.matches(Regex("\\+?[0-9 ()-]+")) }
    ?.filter { it.isDigit() || it == '+' }
    ?.takeIf { value -> value.count(Char::isDigit) >= 3 }
