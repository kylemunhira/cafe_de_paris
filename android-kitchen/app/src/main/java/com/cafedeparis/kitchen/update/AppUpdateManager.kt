package com.cafedeparis.kitchen.update

import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.view.LayoutInflater
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.lifecycle.lifecycleScope
import com.cafedeparis.kitchen.BuildConfig
import com.cafedeparis.kitchen.R
import com.cafedeparis.kitchen.data.ApiClient
import com.cafedeparis.kitchen.data.AppUpdateInfo
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.coroutines.resume

class AppUpdateManager(
    private val activity: AppCompatActivity,
    private val api: ApiClient,
) {
    private var activeDialog: AlertDialog? = null

    /**
     * Check for updates and show a dialog when a newer version is available.
     * @return true if the user may continue using the app, false when a forced update blocks usage.
     */
    suspend fun checkAndPrompt(forceCheck: Boolean = false): Boolean {
        val info = withContext(Dispatchers.IO) {
            api.checkAppVersion(BuildConfig.VERSION_CODE)
        }
        if (!info.updateAvailable || info.apkUrl.isNullOrBlank()) {
            if (forceCheck) {
                withContext(Dispatchers.Main) {
                    Toast.makeText(activity, R.string.update_none, Toast.LENGTH_SHORT).show()
                }
            }
            return !info.forceUpdate
        }
        return withContext(Dispatchers.Main) {
            showUpdateDialog(info)
        }
    }

    private suspend fun showUpdateDialog(info: AppUpdateInfo): Boolean {
        val message = buildString {
            append(
                activity.getString(
                    R.string.update_message,
                    info.latestVersionName,
                    BuildConfig.VERSION_NAME,
                ),
            )
            if (info.releaseNotes.isNotBlank()) {
                append("\n\n")
                append(info.releaseNotes)
            }
        }

        return suspendCancellableCoroutine { continuation ->
            var resumed = false
            fun resumeOnce(value: Boolean) {
                if (!resumed && continuation.isActive) {
                    resumed = true
                    continuation.resume(value)
                }
            }

            val builder = AlertDialog.Builder(activity)
                .setTitle(R.string.update_available_title)
                .setMessage(message)
                .setCancelable(!info.forceUpdate)
                .setPositiveButton(R.string.update_download) { _, _ ->
                    resumeOnce(!info.forceUpdate)
                    startDownload(info)
                }

            if (!info.forceUpdate) {
                builder.setNegativeButton(R.string.update_later) { _, _ ->
                    resumeOnce(true)
                }
            }

            val dialog = builder.create()
            activeDialog = dialog
            dialog.setOnDismissListener {
                activeDialog = null
                if (info.forceUpdate) {
                    resumeOnce(false)
                }
            }
            dialog.show()

            continuation.invokeOnCancellation { dialog.dismiss() }
        }
    }

    private fun startDownload(info: AppUpdateInfo) {
        val apkUrl = info.apkUrl ?: return
        val progressView = LayoutInflater.from(activity).inflate(R.layout.dialog_update_progress, null)
        val messageView = progressView.findViewById<TextView>(R.id.updateProgressMessage)
        val progressBar = progressView.findViewById<ProgressBar>(R.id.updateProgressBar)

        messageView.text = activity.getString(R.string.update_downloading)
        progressBar.isIndeterminate = true

        val progressDialog = AlertDialog.Builder(activity)
            .setTitle(R.string.update_available_title)
            .setView(progressView)
            .setCancelable(false)
            .create()
        progressDialog.show()

        activity.lifecycleScope.launch {
            try {
                val apkFile = File(activity.cacheDir, "kitchen-update.apk")
                withContext(Dispatchers.IO) {
                    api.downloadFile(apkUrl, apkFile)
                }
                progressDialog.dismiss()
                promptInstall(apkFile)
            } catch (error: Exception) {
                progressDialog.dismiss()
                Toast.makeText(
                    activity,
                    activity.getString(R.string.update_download_failed, error.message ?: "Unknown error"),
                    Toast.LENGTH_LONG,
                ).show()
                if (info.forceUpdate) {
                    activity.lifecycleScope.launch {
                        checkAndPrompt(forceCheck = false)
                    }
                }
            }
        }
    }

    private fun promptInstall(apkFile: File) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !activity.packageManager.canRequestPackageInstalls()) {
            AlertDialog.Builder(activity)
                .setTitle(R.string.update_install_permission_title)
                .setMessage(R.string.update_install_permission_message)
                .setPositiveButton(R.string.update_open_settings) { _, _ ->
                    val intent = Intent(
                        Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        Uri.parse("package:${activity.packageName}"),
                    )
                    activity.startActivity(intent)
                }
                .setNegativeButton(android.R.string.cancel, null)
                .show()
            return
        }

        val uri = FileProvider.getUriForFile(
            activity,
            "${activity.packageName}.fileprovider",
            apkFile,
        )
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        activity.startActivity(intent)
    }
}
