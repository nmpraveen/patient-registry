package com.naveenhospital.medtrack.core.network.model

import com.squareup.moshi.JsonAdapter
import com.squareup.moshi.JsonReader
import com.squareup.moshi.JsonWriter
import com.squareup.moshi.Moshi
import com.squareup.moshi.Types
import java.lang.reflect.Type

/** Writes only present PATCH fields while preserving an explicit null value. */
object UpdateCaseRequestDtoJsonAdapterFactory : JsonAdapter.Factory {
    override fun create(type: Type, annotations: Set<Annotation>, moshi: Moshi): JsonAdapter<*>? {
        if (annotations.isNotEmpty() || Types.getRawType(type) != UpdateCaseRequestDto::class.java) return null
        return Adapter
    }

    private object Adapter : JsonAdapter<UpdateCaseRequestDto>() {
        override fun fromJson(reader: JsonReader): UpdateCaseRequestDto {
            throw UnsupportedOperationException("UpdateCaseRequestDto is request-only.")
        }

        override fun toJson(writer: JsonWriter, value: UpdateCaseRequestDto?) {
            requireNotNull(value) { "UpdateCaseRequestDto must not be null." }
            writer.beginObject()
            writer.patch("patient_mode", value.patientMode)
            writer.patch("selected_patient", value.selectedPatient)
            writer.patch("use_temporary_uhid", value.useTemporaryUhid)
            writer.patch("uhid", value.uhid)
            writer.patch("prefix", value.prefix)
            writer.patch("first_name", value.firstName)
            writer.patch("last_name", value.lastName)
            writer.patch("gender", value.gender)
            writer.patch("blood_group", value.bloodGroup)
            writer.patch("date_of_birth", value.dateOfBirth)
            writer.patch("place", value.place)
            writer.patch("age", value.age)
            writer.patch("phone_number", value.phoneNumber)
            writer.patch("alternate_phone_number", value.alternatePhoneNumber)
            writer.patch("category", value.category)
            writer.patch("subcategory", value.subcategory)
            writer.patch("status", value.status)
            writer.patch("diagnosis", value.diagnosis)
            writer.patch("referred_by", value.referredBy)
            writer.patch("notes", value.notes)
            writer.patch("high_risk", value.highRisk)
            writer.patch("ncd_flags", value.ncdFlags)
            writer.patch("anc_high_risk_reasons", value.ancHighRiskReasons)
            writer.patch("rch_number", value.rchNumber)
            writer.patch("rch_bypass", value.rchBypass)
            writer.patch("lmp", value.lmp)
            writer.patch("edd", value.edd)
            writer.patch("usg_edd", value.usgEdd)
            writer.patch("surgical_pathway", value.surgicalPathway)
            writer.patch("surgery_done", value.surgeryDone)
            writer.patch("surgery_date", value.surgeryDate)
            writer.patch("review_frequency", value.reviewFrequency)
            writer.patch("review_date", value.reviewDate)
            writer.patch("gravida", value.gravida)
            writer.patch("para", value.para)
            writer.patch("abortions", value.abortions)
            writer.patch("living", value.living)
            writer.patch("ftnd", value.ftnd)
            writer.patch("lscs", value.lscs)
            writer.patch("client_write_id", value.clientWriteId)
            writer.endObject()
        }
    }
}

private fun JsonWriter.patch(name: String, field: PatchField<*>) {
    if (field !is PatchField.Value) return
    name(name)
    val priorSerializeNulls = serializeNulls
    serializeNulls = true
    try {
        jsonValue(field.value)
    } finally {
        serializeNulls = priorSerializeNulls
    }
}
