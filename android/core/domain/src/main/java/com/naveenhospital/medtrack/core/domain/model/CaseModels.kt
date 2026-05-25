package com.naveenhospital.medtrack.core.domain.model

enum class CaseCategory(val label: String) {
    ANC("ANC"),
    SURGERY("Surgery"),
    MEDICINE("Medicine"),
    OTHER("Other"),
}

enum class CaseStatus(val label: String) {
    ACTIVE("Active"),
    COMPLETED("Completed"),
    CANCELLED("Cancelled"),
    LOSS_TO_FOLLOW_UP("Loss to follow-up"),
}

data class PatientCase(
    val id: String,
    val uhid: String,
    val patientName: String,
    val age: Int? = null,
    val sexLabel: String? = null,
    val place: String? = null,
    val phoneNumber: String? = null,
    val category: CaseCategory,
    val subcategoryValue: String? = null,
    val subcategoryLabel: String? = null,
    val status: CaseStatus,
    val diagnosis: String,
    val nextTaskId: String? = null,
    val nextTaskTitle: String? = null,
    val nextTaskDueDate: String? = null,
    val latestVitalSummary: String? = null,
    val isHighRisk: Boolean,
    val highRiskReasons: List<String> = emptyList(),
)

data class CategoryFilterOption(
    val value: String,
    val label: String,
    val category: CaseCategory,
    val iconPath: String? = null,
    val subcategories: List<SubcategoryFilterOption> = emptyList(),
)

data class SubcategoryFilterOption(
    val value: String,
    val label: String,
    val iconPath: String? = null,
)

data class InboxStats(
    val today: Int = 0,
    val upcoming: Int = 0,
    val overdue: Int = 0,
    val awaiting: Int = 0,
    val red: Int = 0,
)

data class TaskSummary(
    val id: String,
    val title: String,
    val dueDate: String?,
    val status: String,
)

data class PatientTask(
    val id: String,
    val caseId: String,
    val title: String,
    val dueDate: String?,
    val status: String,
    val statusLabel: String,
    val canComplete: Boolean,
)

data class PatientVital(
    val id: String,
    val caseId: String,
    val recordedAt: String,
    val bpSystolic: Int? = null,
    val bpDiastolic: Int? = null,
    val pulse: Int? = null,
    val spo2: Int? = null,
    val weightKg: String? = null,
    val hemoglobin: String? = null,
    val summary: String,
)

data class VitalsThresholdConfig(
    val version: Int,
    val metrics: Map<String, Any?>,
    val statusLabels: Map<String, Map<String, String>>,
) {
    fun evaluateMetric(metricKey: String, rawValue: Double?): VitalStatusResult {
        if (rawValue == null) return result(metricKey, "na")
        val metric = metrics[metricKey].asMap() ?: return result(metricKey, "na")
        val fixedStatus = metric["status"] as? String
        if (!fixedStatus.isNullOrBlank()) return result(metricKey, fixedStatus)

        return when {
            metric.conditions("red").any { it.matches(rawValue) } -> result(metricKey, "red")
            metric.conditions("orange").any { it.matches(rawValue) } -> result(metricKey, "orange")
            metric.condition("green")?.matches(rawValue) == true -> result(metricKey, "green")
            else -> result(metricKey, "na")
        }
    }

    fun evaluateBloodPressure(systolic: Int?, diastolic: Int?): VitalStatusResult {
        if (systolic == null && diastolic == null) return result("blood_pressure", "na")
        val metric = metrics["blood_pressure"].asMap() ?: return result("blood_pressure", "na")
        return when {
            metric.conditions("red").any { it.matchesBloodPressure(systolic, diastolic) } -> result("blood_pressure", "red")
            metric.conditions("orange").any { it.matchesBloodPressure(systolic, diastolic) } -> result("blood_pressure", "orange")
            metric.condition("green")?.matchesBloodPressure(systolic, diastolic) == true -> result("blood_pressure", "green")
            else -> result("blood_pressure", "na")
        }
    }

    private fun result(metricKey: String, status: String): VitalStatusResult =
        VitalStatusResult(
            status = status,
            label = statusLabels[metricKey]?.get(status) ?: status.replaceFirstChar { it.titlecase() },
        )
}

data class VitalStatusResult(
    val status: String,
    val label: String,
)

private fun Any?.asMap(): Map<String, Any?>? =
    (this as? Map<*, *>)?.mapNotNull { (key, value) -> (key as? String)?.let { it to value } }?.toMap()

private fun Map<String, Any?>.condition(key: String): Map<String, Any?>? =
    this[key].asMap()

private fun Map<String, Any?>.conditions(key: String): List<Map<String, Any?>> =
    when (val value = this[key]) {
        is List<*> -> value.mapNotNull { it.asMap() }
        else -> listOfNotNull(value.asMap())
    }

private fun Map<String, Any?>.matches(value: Double): Boolean {
    var checked = false
    for ((key, rawExpected) in this) {
        val expected = rawExpected.asDouble() ?: continue
        checked = true
        val passes = when (key) {
            "min", "gte" -> value >= expected
            "max", "lte" -> value <= expected
            "lt" -> value < expected
            "gt" -> value > expected
            else -> true
        }
        if (!passes) return false
    }
    return checked
}

private fun Map<String, Any?>.matchesBloodPressure(systolic: Int?, diastolic: Int?): Boolean {
    var checked = false
    for ((key, rawExpected) in this) {
        val expected = rawExpected.asDouble() ?: continue
        val value = when {
            key.startsWith("systolic_") -> systolic?.toDouble()
            key.startsWith("diastolic_") -> diastolic?.toDouble()
            else -> null
        } ?: continue
        checked = true
        val passes = when {
            key.endsWith("_gte") -> value >= expected
            key.endsWith("_lte") -> value <= expected
            key.endsWith("_lt") -> value < expected
            key.endsWith("_gt") -> value > expected
            else -> true
        }
        if (!passes) return false
    }
    return checked
}

private fun Any?.asDouble(): Double? =
    when (this) {
        is Number -> toDouble()
        is String -> toDoubleOrNull()
        else -> null
    }
