package com.naveenhospital.medtrack.core.data.repository

import com.naveenhospital.medtrack.core.data.auth.AccountSessionIdentity
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/** Memory-only state. Every result is tied to a verified session incarnation and request. */
class StaffSessionState<T>(private val empty: T) {
    private var generation = 0L
    private var owner: AccountSessionIdentity? = null
    private val mutable = MutableStateFlow(empty)
    val state: StateFlow<T> = mutable

    @Synchronized
    fun activate(identity: AccountSessionIdentity?) {
        generation++
        owner = identity
        mutable.value = empty
    }

    @Synchronized
    fun begin(identity: AccountSessionIdentity): Long {
        if (owner != identity) throw CancellationException("Staff session changed")
        generation++
        mutable.value = empty
        return generation
    }

    @Synchronized
    fun publish(identity: AccountSessionIdentity, request: Long, value: T): Boolean {
        if (owner != identity || generation != request) return false
        mutable.value = value
        return true
    }

    @Synchronized
    fun isCurrent(identity: AccountSessionIdentity): Boolean = owner == identity
}
