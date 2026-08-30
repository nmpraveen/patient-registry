package com.naveenhospital.medtrack.core.data.auth

import android.content.SharedPreferences
import java.lang.reflect.Proxy

internal fun failingCommitPreferences(delegate: SharedPreferences): SharedPreferences =
    Proxy.newProxyInstance(
        SharedPreferences::class.java.classLoader,
        arrayOf(SharedPreferences::class.java),
    ) { _, method, arguments ->
        if (method.name == "edit") {
            failingCommitEditor(delegate.edit())
        } else {
            method.invoke(delegate, *(arguments ?: emptyArray()))
        }
    } as SharedPreferences

private fun failingCommitEditor(delegate: SharedPreferences.Editor): SharedPreferences.Editor {
    lateinit var proxy: SharedPreferences.Editor
    proxy = Proxy.newProxyInstance(
        SharedPreferences.Editor::class.java.classLoader,
        arrayOf(SharedPreferences.Editor::class.java),
    ) { _, method, arguments ->
        when (method.name) {
            "commit" -> false
            "apply" -> Unit
            else -> {
                val result = method.invoke(delegate, *(arguments ?: emptyArray()))
                if (result is SharedPreferences.Editor) proxy else result
            }
        }
    } as SharedPreferences.Editor
    return proxy
}
