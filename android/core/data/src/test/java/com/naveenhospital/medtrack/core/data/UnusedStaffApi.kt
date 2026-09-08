package com.naveenhospital.medtrack.core.data

import com.naveenhospital.medtrack.core.network.api.StaffOperationsApi
import java.lang.reflect.Proxy

/** Existing clinical fake APIs must fail if they accidentally call an operational endpoint. */
fun unusedStaffApi(): StaffOperationsApi = Proxy.newProxyInstance(
    StaffOperationsApi::class.java.classLoader,
    arrayOf(StaffOperationsApi::class.java),
) { _, method, _ -> error("Unexpected staff API call: ${method.name}") } as StaffOperationsApi
