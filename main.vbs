'Version 1.7 - 2026-07-12
'Alteracoes da versao 1.7:
'- Reduzidas as saidas OnRead_ de 113 para 48, mantendo somente sinais essenciais para ML e operacao.
'- Removidos callbacks de aliases, totalizadores brutos redundantes, detalhes pouco relevantes de processo e erros categorizados desativados.
'- Mantidas metricas de carga, memoria, filas, taxas Local/Remote, descarte, reinicio, qualidade da coleta e metadados minimos.
'Alteracoes da versao 1.6:
'- Removida a varredura/classificacao textual de erros do ETL para reduzir tempo de leitura.
'- Mantidos os callbacks antigos de erro por compatibilidade, retornando valores neutros.
'- Mantidas as metricas de contador de scripts do E3Run, incluindo runErrors e runErrorsPerMinute.
'Alteracoes da versao 1.5:
'- Adicionados deltas e taxas por minuto separados para eventos Local e Remote.
'- As taxas usam o timestamp interno dos registros ETL, nunca o horario da leitura.
'- Adicionadas taxas agregadas de entrada, processamento, crescimento e descarte.
'- Adicionadas contagens de erros por intervalo ETL e flags de cobertura da janela.
'- Adicionadas flags de mudanca do arquivo e reinicio dos contadores.
'Alteracoes da versao 1.4:
'- runUptimeMinutes agora retorna somente minutos completos, sem casas decimais.
'Alteracoes da versao 1.3:
'- Adicionado runUptimeMinutes com o tempo total de execucao do E3Run em minutos.
'- O valor textual RUN do E3Run passou a ser usado somente como insumo interno.
'- Removida a coleta de RUN do E3Server; nenhuma conversao de uptime e feita para ele.
'Alteracoes da versao 1.2:
'- Removida a coleta de nome do servidor via WScript.Network e WScript.Shell.
'- Removidos os campos configuraveis de servidor, aplicacao e ambiente.
'- Mantidas somente metricas do ETL, metadados do arquivo e calculos em memoria.
'Alteracoes da versao 1.1:
'- Adicionadas metricas completas de processo para E3Run e E3Server.
'- Adicionadas metricas de scripts, eventos Local/Remote e indicadores globais do log.
'- Adicionados metadados da coleta, arquivo ETL e identificacao do ambiente.
'- Adicionadas flags de presenca dos blocos e variacoes por minuto entre coletas.
'- Mantida a leitura incremental em memoria, sem WMI e sem arquivos temporarios.
'- sampleTimestamp representa o instante da coleta; o timestamp interno do evento ETL nao e decodificado.
Option Explicit

Const ETL_SOURCE_FOLDER = "F:\eeLogs\E3\E3"
Const LOG_FILE_PREFIX = "E3_"
Const INITIAL_TAIL_READ_MB = 1
Const TAIL_READ_STEP_MB = 1
Const MAX_TAIL_READ_MB = 1
Const MAX_TEXT_AFTER_MARKER = 900
Const MAX_SKIP_CHUNK = 50000000
Const USE_INCREMENTAL_TAIL_READ = True
Const ROLLING_BUFFER_MAX_CHARS = 1048576
Const ETL_QPC_TICKS_PER_SECOND = 10000000

Const ForReading = 1
Const TristateFalse = 0

Const BAD_QUALITY = 20
Const NOT_FOUND = "(nao encontrado)"

Dim fsoGlobal
Dim tailStreamGlobal
Dim tailFilePathGlobal
Dim tailFileSizeGlobal
Dim rollingTailTextGlobal


Dim runCPU
Dim runPVT
Dim runHDL
Dim runTRD
Dim runVTL
Dim runWKS
Dim runGDI
Dim runUSR
Dim runPGF
Dim runRUN
Dim runUptimeMinutes
Dim runRestartDetected
Dim runOccupancy
Dim runScriptExecs
Dim runScriptTime
Dim runAvgScriptTime
Dim runPendingEvents
Dim runDiscardedEvents
Dim runLocalQueued
Dim runLocalHandled
Dim runLocalPending
Dim runLocalDiscarded
Dim runRemoteQueued
Dim runRemoteHandled
Dim runRemotePending
Dim runRemoteDiscarded
Dim runLocalQueuedDelta
Dim runLocalHandledDelta
Dim runLocalPendingDelta
Dim runLocalDiscardedDelta
Dim runRemoteQueuedDelta
Dim runRemoteHandledDelta
Dim runRemotePendingDelta
Dim runRemoteDiscardedDelta
Dim runLocalQueuedPerMinute
Dim runLocalHandledPerMinute
Dim runLocalPendingPerMinute
Dim runLocalDiscardedPerMinute
Dim runRemoteQueuedPerMinute
Dim runRemoteHandledPerMinute
Dim runRemotePendingPerMinute
Dim runRemoteDiscardedPerMinute
Dim runLocalQueueGrowthPerMinute
Dim runRemoteQueueGrowthPerMinute
Dim runLocalDiscardPercent
Dim runRemoteDiscardPercent
Dim runQueuedPerMinute
Dim runHandledPerMinute
Dim runQueueGrowthPerMinute
Dim runDiscardPercent
Dim linkEventsIntervalMinutes
Dim linkEventsIntervalAvailable
Dim runLocalCountersReset
Dim runRemoteCountersReset
Dim runAnyCounterReset
Dim runErrors
Dim runErrorsPerMinute
Dim runMemory
Dim runPageFaults
Dim globalCPU
Dim globalHandles
Dim globalProcesses
Dim globalThreads
Dim driveCFreeMB
Dim ioQueuePending
Dim ioQueueAvgDelay
Dim serverStatus
Dim serverCPU
Dim serverHDL
Dim serverPVT
Dim serverTRD
Dim serverVTL
Dim serverWKS
Dim serverGDI
Dim serverUSR
Dim serverPGF
Dim collectionTimestamp
Dim sampleTimestamp
Dim etlLastModified
Dim sampleAgeSeconds
Dim etlFileSizeBytes
Dim etlFileSizeMB
Dim etlFileChanged
Dim previousEtlPath
Dim timeoutErrorCount
Dim disconnectErrorCount
Dim databaseErrorCount
Dim rpcComErrorCount
Dim driverErrorCount
Dim relevantErrorCount
Dim errorIntervalMinutes
Dim errorWindowActualMinutes
Dim errorIntervalComplete
Dim foundProcessSummary
Dim foundE3RunProcess
Dim foundE3RunScripts
Dim foundE3RunLinkEvents
Dim foundIOQueue
Dim foundE3Server
Dim deltaRunPVTPerMinute
Dim deltaRunHDLPerMinute
Dim deltaRunTRDPerMinute
Dim deltaRunPGFPerMinute
Dim deltaRunErrorsPerMinute
Dim deltaRunPendingPerMinute
Dim deltaRunDiscardedPerMinute
Dim previousRunProcessTime
Dim previousRunScriptsTime
Dim previousRunProcessSignature
Dim previousRunScriptsSignature
Dim previousRunPVT
Dim previousRunHDL
Dim previousRunTRD
Dim previousRunPGF
Dim previousRunErrors
Dim statusGlobal
Dim statusMsgGlobal
Dim fileRead
Dim totalTime
Dim readModeGlobal


Sub OnStart()
    ResetOutputs "Aguardando leitura do trigger"

    ResetPreviousMetrics

    Err.Clear
    Set fsoGlobal = CreateObject("Scripting.FileSystemObject")

    If Err.Number <> 0 Then
        statusGlobal = "Fail"
        statusMsgGlobal = "Erro criando FileSystemObject: " & Err.Description
        Err.Clear
    End If
End Sub

Sub OnStop()
    CloseTailStream
    Set fsoGlobal = Nothing
End Sub

Sub ResetOutputs(msg)
    runCPU = NOT_FOUND
    runPVT = NOT_FOUND
    runHDL = NOT_FOUND
    runTRD = NOT_FOUND
    runVTL = NOT_FOUND
    runWKS = NOT_FOUND
    runGDI = NOT_FOUND
    runUSR = NOT_FOUND
    runPGF = NOT_FOUND
    runRUN = NOT_FOUND
    runUptimeMinutes = NOT_FOUND
    runRestartDetected = "0"
    runOccupancy = NOT_FOUND
    runScriptExecs = NOT_FOUND
    runScriptTime = NOT_FOUND
    runAvgScriptTime = NOT_FOUND
    runPendingEvents = NOT_FOUND
    runDiscardedEvents = NOT_FOUND
    runLocalQueued = NOT_FOUND
    runLocalHandled = NOT_FOUND
    runLocalPending = NOT_FOUND
    runLocalDiscarded = NOT_FOUND
    runRemoteQueued = NOT_FOUND
    runRemoteHandled = NOT_FOUND
    runRemotePending = NOT_FOUND
    runRemoteDiscarded = NOT_FOUND
    ResetLinkIntervalOutputs
    runErrors = NOT_FOUND
    runErrorsPerMinute = NOT_FOUND
    runMemory = NOT_FOUND
    runPageFaults = NOT_FOUND
    globalCPU = NOT_FOUND
    globalHandles = NOT_FOUND
    globalProcesses = NOT_FOUND
    globalThreads = NOT_FOUND
    driveCFreeMB = NOT_FOUND
    ioQueuePending = NOT_FOUND
    ioQueueAvgDelay = NOT_FOUND

    serverStatus = NOT_FOUND
    serverCPU = NOT_FOUND
    serverHDL = NOT_FOUND
    serverPVT = NOT_FOUND
    serverTRD = NOT_FOUND
    serverVTL = NOT_FOUND
    serverWKS = NOT_FOUND
    serverGDI = NOT_FOUND
    serverUSR = NOT_FOUND
    serverPGF = NOT_FOUND
    collectionTimestamp = ""
    sampleTimestamp = ""
    etlLastModified = ""
    sampleAgeSeconds = NOT_FOUND
    etlFileSizeBytes = NOT_FOUND
    etlFileSizeMB = NOT_FOUND
    etlFileChanged = "0"
    timeoutErrorCount = "0"
    disconnectErrorCount = "0"
    databaseErrorCount = "0"
    rpcComErrorCount = "0"
    driverErrorCount = "0"
    relevantErrorCount = "0"
    errorIntervalMinutes = NOT_FOUND
    errorWindowActualMinutes = NOT_FOUND
    errorIntervalComplete = "0"

    foundProcessSummary = "0"
    foundE3RunProcess = "0"
    foundE3RunScripts = "0"
    foundE3RunLinkEvents = "0"
    foundIOQueue = "0"
    foundE3Server = "0"

    deltaRunPVTPerMinute = NOT_FOUND
    deltaRunHDLPerMinute = NOT_FOUND
    deltaRunTRDPerMinute = NOT_FOUND
    deltaRunPGFPerMinute = NOT_FOUND
    deltaRunErrorsPerMinute = NOT_FOUND
    deltaRunPendingPerMinute = NOT_FOUND
    deltaRunDiscardedPerMinute = NOT_FOUND

    statusGlobal = "Idle"
    statusMsgGlobal = msg
    fileRead = ""
    totalTime = ""
    readModeGlobal = ""
End Sub

Sub ResetPreviousMetrics()
    previousRunProcessTime = Empty
    previousRunScriptsTime = Empty
    previousRunProcessSignature = ""
    previousRunScriptsSignature = ""
    previousEtlPath = ""
    previousRunPVT = NOT_FOUND
    previousRunHDL = NOT_FOUND
    previousRunTRD = NOT_FOUND
    previousRunPGF = NOT_FOUND
    previousRunErrors = NOT_FOUND
End Sub

Sub ResetLinkIntervalOutputs()
    runLocalQueuedDelta = NOT_FOUND
    runLocalHandledDelta = NOT_FOUND
    runLocalPendingDelta = NOT_FOUND
    runLocalDiscardedDelta = NOT_FOUND
    runRemoteQueuedDelta = NOT_FOUND
    runRemoteHandledDelta = NOT_FOUND
    runRemotePendingDelta = NOT_FOUND
    runRemoteDiscardedDelta = NOT_FOUND
    runLocalQueuedPerMinute = NOT_FOUND
    runLocalHandledPerMinute = NOT_FOUND
    runLocalPendingPerMinute = NOT_FOUND
    runLocalDiscardedPerMinute = NOT_FOUND
    runRemoteQueuedPerMinute = NOT_FOUND
    runRemoteHandledPerMinute = NOT_FOUND
    runRemotePendingPerMinute = NOT_FOUND
    runRemoteDiscardedPerMinute = NOT_FOUND
    runLocalQueueGrowthPerMinute = NOT_FOUND
    runRemoteQueueGrowthPerMinute = NOT_FOUND
    runLocalDiscardPercent = NOT_FOUND
    runRemoteDiscardPercent = NOT_FOUND
    runQueuedPerMinute = NOT_FOUND
    runHandledPerMinute = NOT_FOUND
    runQueueGrowthPerMinute = NOT_FOUND
    runDiscardPercent = NOT_FOUND
    linkEventsIntervalMinutes = NOT_FOUND
    linkEventsIntervalAvailable = "0"
    runLocalCountersReset = "0"
    runRemoteCountersReset = "0"
    runAnyCounterReset = "0"
End Sub

Sub ResetReadIndicators()
    runRestartDetected = "0"
    foundProcessSummary = "0"
    foundE3RunProcess = "0"
    foundE3RunScripts = "0"
    foundE3RunLinkEvents = "0"
    foundIOQueue = "0"
    foundE3Server = "0"
    etlFileChanged = "0"
    timeoutErrorCount = "0"
    disconnectErrorCount = "0"
    databaseErrorCount = "0"
    rpcComErrorCount = "0"
    driverErrorCount = "0"
    relevantErrorCount = "0"
    errorIntervalMinutes = NOT_FOUND
    errorWindowActualMinutes = NOT_FOUND
    errorIntervalComplete = "0"
    ResetLinkIntervalOutputs
End Sub

Function FormatDateTimeIso(ByVal value)
    FormatDateTimeIso = CStr(Year(value)) & "-" & Pad2(Month(value)) & "-" & Pad2(Day(value)) & _
        "T" & Pad2(Hour(value)) & ":" & Pad2(Minute(value)) & ":" & Pad2(Second(value))
End Function

Function Pad2(ByVal value)
    Pad2 = Right("0" & CStr(value), 2)
End Function

Sub TrackEtlFileChange(ByVal currentPath)
    etlFileChanged = "0"

    If previousEtlPath <> "" Then
        If StrComp(previousEtlPath, currentPath, vbTextCompare) <> 0 Then etlFileChanged = "1"
    End If

    previousEtlPath = currentPath
End Sub

Sub UpdateValueIfFound(ByRef currentValue, ByVal newValue)
    If newValue <> "" And newValue <> NOT_FOUND Then
        currentValue = newValue
    End If
End Sub

Sub OnRead_trigger(r, v)

    On Error Resume Next

    Dim scriptStartTime
    Dim scriptElapsedSeconds
    Dim statusMsg
    Dim latestPath
    Dim latestSize
    Dim latestModified
    Dim currentSampleTime
    Dim runText
    Dim processSummaryText
    Dim e3RunProcessText
    Dim e3RunScriptsText
    Dim e3RunPreviousScriptsText
    Dim e3RunLinkEventsText
    Dim e3RunPreviousLinkEventsText
    Dim linkInterval
    Dim ioQueueText
    Dim e3ServerText
    Dim tailUsedMb

    statusGlobal = "Running"
    statusMsgGlobal = "Executando leitura do ETL"
    totalTime = ""
    currentSampleTime = Now
    collectionTimestamp = FormatDateTimeIso(currentSampleTime)
    ResetReadIndicators

    scriptStartTime = Timer
    statusMsg = "OK"

    If EnsureFileSystem(statusMsg) Then

        If FindLatestEtl(latestPath, latestSize, latestModified, statusMsg) Then

            fileRead = latestPath
            TrackEtlFileChange latestPath
            etlFileSizeBytes = CStr(latestSize)
            etlFileSizeMB = FormatMetricNumber(CDbl(latestSize) / 1048576)
            etlLastModified = FormatDateTimeIso(latestModified)
            sampleTimestamp = collectionTimestamp
            sampleAgeSeconds = CStr(DateDiff("s", latestModified, currentSampleTime))
            If CLng(sampleAgeSeconds) < 0 Then sampleAgeSeconds = "0"

            If ReadAdaptiveTail(latestPath, latestSize, processSummaryText, e3RunProcessText, e3RunScriptsText, e3RunPreviousScriptsText, e3RunLinkEventsText, e3RunPreviousLinkEventsText, linkInterval, ioQueueText, e3ServerText, tailUsedMb, statusMsg) Then

                If processSummaryText <> "" Then
                    foundProcessSummary = "1"
                    UpdateValueIfFound runMemory, ExtractNumericMetric(processSummaryText, "MemoryLoad")
                    UpdateValueIfFound runPageFaults, ExtractNumericMetric(processSummaryText, "PageFaults")
                    UpdateValueIfFound globalCPU, ExtractNumericMetric(processSummaryText, "CPU")
                    UpdateValueIfFound globalHandles, ExtractNumericMetric(processSummaryText, "Handles")
                    UpdateValueIfFound globalProcesses, ExtractNumericMetric(processSummaryText, "Processes")
                    UpdateValueIfFound globalThreads, ExtractNumericMetric(processSummaryText, "Threads")
                    UpdateValueIfFound driveCFreeMB, ExtractNumericMetric(processSummaryText, "DriveC")
                    UpdateValueIfFound serverStatus, ExtractProcessStatus(processSummaryText, "E3Server")
                End If

                If e3RunProcessText <> "" Then
                    foundE3RunProcess = "1"
                    UpdateValueIfFound runCPU, ExtractNumericMetric(e3RunProcessText, "CPU")
                    UpdateValueIfFound runPVT, ExtractNumericMetric(e3RunProcessText, "PVT")
                    UpdateValueIfFound runHDL, ExtractNumericMetric(e3RunProcessText, "HDL")
                    UpdateValueIfFound runTRD, ExtractNumericMetric(e3RunProcessText, "TRD")
                    UpdateValueIfFound runVTL, ExtractNumericMetric(e3RunProcessText, "VTL")
                    UpdateValueIfFound runWKS, ExtractNumericMetric(e3RunProcessText, "WKS")
                    UpdateValueIfFound runGDI, ExtractNumericMetric(e3RunProcessText, "GDI")
                    UpdateValueIfFound runUSR, ExtractNumericMetric(e3RunProcessText, "USR")
                    UpdateValueIfFound runPGF, ExtractNumericMetric(e3RunProcessText, "PGF")
                    runText = ExtractMetric(e3RunProcessText, "RUN")
                    UpdateValueIfFound runRUN, runText
                    UpdateValueIfFound runUptimeMinutes, ConvertRunToMinutes(runText)
                End If

                If e3RunScriptsText <> "" Then
                    foundE3RunScripts = "1"
                    UpdateValueIfFound runOccupancy, ExtractNumericMetric(e3RunScriptsText, "Occupancy")
                    UpdateValueIfFound runScriptExecs, ExtractNumericMetric(e3RunScriptsText, "Execs")
                    UpdateValueIfFound runScriptTime, ExtractNumericMetric(e3RunScriptsText, "Time")
                    UpdateValueIfFound runErrors, ExtractNumericMetric(e3RunScriptsText, "Errors")
                    UpdateValueIfFound runAvgScriptTime, CalculateAverageMetric(runScriptTime, runScriptExecs)
                    UpdateValueIfFound runErrorsPerMinute, CalculateErrorsPerMinute(e3RunScriptsText, e3RunPreviousScriptsText)
                End If

                If e3RunLinkEventsText <> "" Then
                    foundE3RunLinkEvents = "1"
                    UpdateValueIfFound runLocalQueued, ExtractSectionNumericMetric(e3RunLinkEventsText, "Local:", "Remote:", "Queued")
                    UpdateValueIfFound runLocalHandled, ExtractSectionNumericMetric(e3RunLinkEventsText, "Local:", "Remote:", "Handled")
                    UpdateValueIfFound runLocalDiscarded, ExtractSectionNumericMetric(e3RunLinkEventsText, "Local:", "Remote:", "Discarded")
                    UpdateValueIfFound runLocalPending, ExtractSectionNumericMetric(e3RunLinkEventsText, "Local:", "Remote:", "Pending")
                    UpdateValueIfFound runRemoteQueued, ExtractSectionNumericMetric(e3RunLinkEventsText, "Remote:", "", "Queued")
                    UpdateValueIfFound runRemoteHandled, ExtractSectionNumericMetric(e3RunLinkEventsText, "Remote:", "", "Handled")
                    UpdateValueIfFound runRemoteDiscarded, ExtractSectionNumericMetric(e3RunLinkEventsText, "Remote:", "", "Discarded")
                    UpdateValueIfFound runRemotePending, ExtractSectionNumericMetric(e3RunLinkEventsText, "Remote:", "", "Pending")
                    UpdateValueIfFound runPendingEvents, SumMetricValues(e3RunLinkEventsText, "Pending", 2)
                    UpdateValueIfFound runDiscardedEvents, SumMetricValues(e3RunLinkEventsText, "Discarded", 2)
                    UpdateLinkMetricsFromLog e3RunLinkEventsText, e3RunPreviousLinkEventsText, linkInterval
                End If

                If ioQueueText <> "" Then
                    foundIOQueue = "1"
                    UpdateValueIfFound ioQueuePending, ExtractNumericMetric(ioQueueText, "Pending")
                    UpdateValueIfFound ioQueueAvgDelay, ExtractNumericMetric(ioQueueText, "AvgDelay")
                End If

                If e3ServerText <> "" Then
                    foundE3Server = "1"
                    If serverStatus = NOT_FOUND Then serverStatus = "1"
                    UpdateValueIfFound serverCPU, ExtractNumericMetric(e3ServerText, "CPU")
                    UpdateValueIfFound serverPVT, ExtractNumericMetric(e3ServerText, "PVT")
                    UpdateValueIfFound serverHDL, ExtractNumericMetric(e3ServerText, "HDL")
                    UpdateValueIfFound serverTRD, ExtractNumericMetric(e3ServerText, "TRD")
                    UpdateValueIfFound serverVTL, ExtractNumericMetric(e3ServerText, "VTL")
                    UpdateValueIfFound serverWKS, ExtractNumericMetric(e3ServerText, "WKS")
                    UpdateValueIfFound serverGDI, ExtractNumericMetric(e3ServerText, "GDI")
                    UpdateValueIfFound serverUSR, ExtractNumericMetric(e3ServerText, "USR")
                    UpdateValueIfFound serverPGF, ExtractNumericMetric(e3ServerText, "PGF")
                End If

                UpdateDerivedMetrics currentSampleTime
                UpdateAnyCounterResetFlag

                statusGlobal = "Success"
                statusMsgGlobal = "Leitura concluida; tail=" & CStr(tailUsedMb) & " MB; modo=" & readModeGlobal

            Else
                statusGlobal = "Fail"
                statusMsgGlobal = statusMsg
            End If

        Else
            statusGlobal = "Fail"
            statusMsgGlobal = statusMsg
        End If

    Else
        statusGlobal = "Fail"
        statusMsgGlobal = statusMsg
    End If

    scriptElapsedSeconds = Timer - scriptStartTime

    If scriptElapsedSeconds < 0 Then
        scriptElapsedSeconds = scriptElapsedSeconds + 86400
    End If

    totalTime = FormatMetricNumber(scriptElapsedSeconds)

    v.Value = statusGlobal

    If statusGlobal <> "Success" Then
        v.Quality = BAD_QUALITY
    End If

End Sub

Function EnsureFileSystem(ByRef statusMsg)
    EnsureFileSystem = False

    If Not fsoGlobal Is Nothing Then
        EnsureFileSystem = True
        Exit Function
    End If

    Err.Clear
    Set fsoGlobal = CreateObject("Scripting.FileSystemObject")

    If Err.Number <> 0 Then
        statusMsg = "Erro criando FileSystemObject: " & Err.Description
        Err.Clear
    Else
        EnsureFileSystem = True
    End If
End Function

Function FindLatestEtl(ByRef latestPath, ByRef latestSize, ByRef latestModified, ByRef statusMsg)
    Dim folder
    Dim file
    Dim fileName
    Dim latestDate

    FindLatestEtl = False
    latestPath = ""
    latestSize = 0
    latestModified = CDate("1900-01-01")
    latestDate = CDate("1900-01-01")

    If Not fsoGlobal.FolderExists(ETL_SOURCE_FOLDER) Then
        statusMsg = "Pasta ETL nao encontrada: " & ETL_SOURCE_FOLDER
        Exit Function
    End If

    Set folder = fsoGlobal.GetFolder(ETL_SOURCE_FOLDER)

    For Each file In folder.Files
        fileName = CStr(file.Name)

        If LCase(Right(fileName, 4)) = ".etl" Then
            If LOG_FILE_PREFIX = "" Or LCase(Left(fileName, Len(LOG_FILE_PREFIX))) = LCase(LOG_FILE_PREFIX) Then
                If file.DateLastModified > latestDate Then
                    latestDate = file.DateLastModified
                    latestPath = file.Path
                    latestSize = file.Size
                    latestModified = file.DateLastModified
                End If
            End If
        End If
    Next

    If latestPath = "" Then
        statusMsg = "Nenhum ETL encontrado em " & ETL_SOURCE_FOLDER & " com prefixo " & LOG_FILE_PREFIX
        Exit Function
    End If

    FindLatestEtl = True
End Function

Function ReadAdaptiveTail(ByVal latestPath, ByVal latestSize, ByRef processSummaryText, ByRef e3RunProcessText, ByRef e3RunScriptsText, ByRef e3RunPreviousScriptsText, ByRef e3RunLinkEventsText, ByRef e3RunPreviousLinkEventsText, ByRef linkInterval, ByRef ioQueueText, ByRef e3ServerText, ByRef tailUsedMb, ByRef statusMsg)
    Dim tailReadMb
    Dim stepMb
    Dim maxTailMb
    Dim rawData
    Dim scriptsPos
    Dim linkEventsPos
    Dim previousLinkEventsPos

    ReadAdaptiveTail = False
    processSummaryText = ""
    e3RunProcessText = ""
    e3RunScriptsText = ""
    e3RunPreviousScriptsText = ""
    e3RunLinkEventsText = ""
    e3RunPreviousLinkEventsText = ""
    linkInterval = 0
    ioQueueText = ""
    e3ServerText = ""
    tailUsedMb = 0

    tailReadMb = INITIAL_TAIL_READ_MB
    stepMb = TAIL_READ_STEP_MB
    maxTailMb = MAX_TAIL_READ_MB

    If tailReadMb < 1 Then tailReadMb = 1
    If stepMb < 1 Then stepMb = tailReadMb
    If maxTailMb < tailReadMb Then maxTailMb = tailReadMb

    Do
        If Not ReadTailWindow(latestPath, latestSize, tailReadMb, rawData, statusMsg) Then
            Exit Function
        End If

        tailUsedMb = tailReadMb
        processSummaryText = LatestTextAfter(rawData, "ProcessInfo: E3Run")
        e3RunProcessText = LatestTextAfter(rawData, "ProcessInfo.E3RUN")
        e3RunScriptsText = LatestTextAfterWithPosition(rawData, "Scripts.E3RUN", scriptsPos)
        e3RunPreviousScriptsText = ""

        If scriptsPos > 1 Then
            e3RunPreviousScriptsText = LatestTextAfterBefore(rawData, "Scripts.E3RUN", scriptsPos - 1)
        End If

        e3RunLinkEventsText = LatestTextAfterWithPosition(rawData, "LinkEvents.E3Run", linkEventsPos)
        ioQueueText = LatestTextAfter(rawData, "IOQueue:")
        e3ServerText = LatestTextAfter(rawData, "ProcessInfo.E3SERVER")

        If e3RunProcessText <> "" And e3RunScriptsText <> "" And e3RunLinkEventsText <> "" And e3ServerText <> "" Then
            Exit Do
        End If

        If CLng(CDbl(tailReadMb) * 1024 * 1024) >= latestSize Then
            Exit Do
        End If

        If tailReadMb >= maxTailMb Then
            Exit Do
        End If

        tailReadMb = tailReadMb + stepMb
        If tailReadMb > maxTailMb Then tailReadMb = maxTailMb
    Loop

    If linkEventsPos > 1 Then
        e3RunPreviousLinkEventsText = LatestTextAfterBeforeWithPosition(rawData, "LinkEvents.E3Run", linkEventsPos - 1, previousLinkEventsPos)
        linkInterval = CalculateEtlIntervalMinutes(rawData, previousLinkEventsPos, linkEventsPos)
    End If

    ReadAdaptiveTail = True
End Function

Function ReadTailWindow(ByVal latestPath, ByVal latestSize, ByVal tailReadMb, ByRef rawData, ByRef statusMsg)
    readModeGlobal = ""

    If USE_INCREMENTAL_TAIL_READ Then
        If ReadTailWindowIncremental(latestPath, latestSize, tailReadMb, rawData, statusMsg) Then
            ReadTailWindow = True
            Exit Function
        End If

        CloseTailStream
    End If

    ReadTailWindow = ReadTailWindowWithTextStream(latestPath, latestSize, tailReadMb, rawData, statusMsg)
End Function

Function ReadTailWindowIncremental(ByVal latestPath, ByVal latestSize, ByVal tailReadMb, ByRef rawData, ByRef statusMsg)
    Dim tailBytes
    Dim skipBytes
    Dim file
    Dim newBytes
    Dim newData

    On Error Resume Next

    ReadTailWindowIncremental = False
    rawData = ""

    tailBytes = CLng(CDbl(tailReadMb) * 1024 * 1024)

    If latestSize < tailBytes Then
        tailBytes = latestSize
    End If

    If tailStreamGlobal Is Nothing Then
        If Not OpenIncrementalTailStream(latestPath, latestSize, tailBytes, statusMsg) Then
            Exit Function
        End If

        rawData = rollingTailTextGlobal
        ReadTailWindowIncremental = True
        Exit Function
    End If

    If StrComp(tailFilePathGlobal, latestPath, vbTextCompare) <> 0 Or latestSize < tailFileSizeGlobal Then
        CloseTailStream

        If Not OpenIncrementalTailStream(latestPath, latestSize, tailBytes, statusMsg) Then
            Exit Function
        End If

        rawData = rollingTailTextGlobal
        ReadTailWindowIncremental = True
        Exit Function
    End If

    newBytes = latestSize - tailFileSizeGlobal

    If newBytes > 0 Then
        readModeGlobal = "inc-read"
        Err.Clear
        newData = tailStreamGlobal.Read(CLng(newBytes))

        If Err.Number <> 0 Then
            statusMsg = "Erro lendo incremento do ETL: " & Err.Description
            Err.Clear
            Exit Function
        End If

        If Len(newData) > 0 Then
            rollingTailTextGlobal = rollingTailTextGlobal & newData
            TrimRollingTailBuffer
        End If

        tailFileSizeGlobal = latestSize
    Else
        readModeGlobal = "inc-cache"
    End If

    rawData = rollingTailTextGlobal
    ReadTailWindowIncremental = True
End Function

Function OpenIncrementalTailStream(ByVal latestPath, ByVal latestSize, ByVal tailBytes, ByRef statusMsg)
    Dim file
    Dim ts
    Dim skipBytes
    Dim remainingSkip
    Dim skipChunk

    On Error Resume Next

    OpenIncrementalTailStream = False

    skipBytes = latestSize - tailBytes
    If skipBytes < 0 Then skipBytes = 0

    Err.Clear
    Set file = fsoGlobal.GetFile(latestPath)
    Set ts = file.OpenAsTextStream(ForReading, TristateFalse)

    If Err.Number <> 0 Then
        statusMsg = "Erro abrindo ETL em modo texto ANSI: " & latestPath & " - " & Err.Description
        Err.Clear
        Exit Function
    End If

    remainingSkip = skipBytes

    Do While remainingSkip > 0
        skipChunk = remainingSkip
        If skipChunk > MAX_SKIP_CHUNK Then skipChunk = MAX_SKIP_CHUNK

        Err.Clear
        ts.Skip CLng(skipChunk)

        If Err.Number <> 0 Then
            statusMsg = "Erro pulando para a parte recente do ETL: " & Err.Description
            Err.Clear
            ts.Close
            Exit Function
        End If

        remainingSkip = remainingSkip - skipChunk
    Loop

    Err.Clear
    rollingTailTextGlobal = ts.Read(CLng(tailBytes))

    If Err.Number <> 0 Then
        statusMsg = "Erro lendo tail inicial do ETL: " & Err.Description
        Err.Clear
        ts.Close
        Exit Function
    End If

    Set tailStreamGlobal = ts
    tailFilePathGlobal = latestPath
    tailFileSizeGlobal = latestSize
    TrimRollingTailBuffer
    readModeGlobal = "inc-open"

    OpenIncrementalTailStream = True
End Function

Function ReadTailWindowWithTextStream(ByVal latestPath, ByVal latestSize, ByVal tailReadMb, ByRef rawData, ByRef statusMsg)
    Dim file
    Dim ts
    Dim tailBytes
    Dim skipBytes
    Dim remainingSkip
    Dim skipChunk

    On Error Resume Next

    ReadTailWindowWithTextStream = False
    rawData = ""
    readModeGlobal = "fallback-text"

    tailBytes = CLng(CDbl(tailReadMb) * 1024 * 1024)

    If latestSize < tailBytes Then
        tailBytes = latestSize
    End If

    skipBytes = latestSize - tailBytes
    If skipBytes < 0 Then skipBytes = 0

    Err.Clear
    Set file = fsoGlobal.GetFile(latestPath)
    Set ts = file.OpenAsTextStream(ForReading, TristateFalse)

    If Err.Number <> 0 Then
        statusMsg = "Erro abrindo ETL em modo texto ANSI: " & latestPath & " - " & Err.Description
        Err.Clear
        Exit Function
    End If

    remainingSkip = skipBytes

    Do While remainingSkip > 0
        skipChunk = remainingSkip
        If skipChunk > MAX_SKIP_CHUNK Then skipChunk = MAX_SKIP_CHUNK

        Err.Clear
        ts.Skip CLng(skipChunk)

        If Err.Number <> 0 Then
            statusMsg = "Erro pulando para a parte recente do ETL: " & Err.Description
            Err.Clear
            ts.Close
            Exit Function
        End If

        remainingSkip = remainingSkip - skipChunk
    Loop

    Err.Clear
    rawData = ts.Read(CLng(tailBytes))

    If Err.Number <> 0 Then
        statusMsg = "Erro lendo os ultimos " & CStr(tailReadMb) & " MB do ETL: " & Err.Description
        Err.Clear
        ts.Close
        Exit Function
    End If

    ts.Close
    ReadTailWindowWithTextStream = True
End Function

Sub TrimRollingTailBuffer()
    If Len(rollingTailTextGlobal) > ROLLING_BUFFER_MAX_CHARS Then
        rollingTailTextGlobal = Right(rollingTailTextGlobal, ROLLING_BUFFER_MAX_CHARS)
    End If
End Sub

Sub CloseTailStream()
    On Error Resume Next

    If Not tailStreamGlobal Is Nothing Then
        tailStreamGlobal.Close
    End If

    Set tailStreamGlobal = Nothing
    tailFilePathGlobal = ""
    tailFileSizeGlobal = 0
    rollingTailTextGlobal = ""
    Err.Clear
End Sub

Function LatestTextAfter(ByVal rawData, ByVal marker)
    Dim markerPos

    LatestTextAfter = LatestTextAfterWithPosition(rawData, marker, markerPos)
End Function

Function LatestTextAfterWithPosition(ByVal rawData, ByVal marker, ByRef markerPos)
    markerPos = InStrRev(rawData, marker, -1, vbTextCompare)
    LatestTextAfterWithPosition = TextAfterPosition(rawData, markerPos)
End Function

Function LatestTextAfterBefore(ByVal rawData, ByVal marker, ByVal endPos)
    Dim pos

    LatestTextAfterBefore = ""

    If endPos <= 0 Then Exit Function
    If endPos > Len(rawData) Then endPos = Len(rawData)

    pos = InStrRev(rawData, marker, endPos, vbTextCompare)
    LatestTextAfterBefore = TextAfterPosition(rawData, pos)
End Function

Function LatestTextAfterBeforeWithPosition(ByVal rawData, ByVal marker, ByVal endPos, ByRef markerPos)
    markerPos = 0
    LatestTextAfterBeforeWithPosition = ""

    If endPos <= 0 Then Exit Function
    If endPos > Len(rawData) Then endPos = Len(rawData)

    markerPos = InStrRev(rawData, marker, endPos, vbTextCompare)
    LatestTextAfterBeforeWithPosition = TextAfterPosition(rawData, markerPos)
End Function

Function TextAfterPosition(ByVal rawData, ByVal pos)
    Dim text

    TextAfterPosition = ""
    If pos <= 0 Then Exit Function

    text = Mid(rawData, pos, MAX_TEXT_AFTER_MARKER)
    text = Replace(text, Chr(0), " ")
    text = Replace(text, vbCr, " ")
    text = Replace(text, vbLf, " ")
    text = Replace(text, vbTab, " ")

    TextAfterPosition = text
End Function

Function E3ProviderGuidPattern()
    E3ProviderGuidPattern = Chr(14) & Chr(116) & Chr(184) & Chr(235) & _
        Chr(209) & Chr(221) & Chr(120) & Chr(68) & Chr(163) & Chr(92) & _
        Chr(49) & Chr(46) & Chr(108) & Chr(149) & Chr(118) & Chr(204)
End Function

Function ExtractEventQpc(ByVal rawData, ByVal guidPos)
    Dim i
    Dim byteValue
    Dim multiplier
    Dim result

    On Error Resume Next

    ExtractEventQpc = 0
    If guidPos <= 8 Then Exit Function

    result = 0
    multiplier = 1

    For i = 0 To 7
        Err.Clear
        byteValue = Asc(Mid(rawData, guidPos - 8 + i, 1))
        If Err.Number <> 0 Then
            Err.Clear
            Exit Function
        End If

        If byteValue < 0 Then byteValue = byteValue + 256
        result = result + (CDbl(byteValue) * multiplier)
        multiplier = multiplier * 256
    Next

    ExtractEventQpc = result
End Function

Function EventQpcForMarker(ByVal rawData, ByVal markerPos)
    Dim guidPos
    Dim guidPattern

    EventQpcForMarker = 0
    If markerPos <= 0 Then Exit Function

    guidPattern = E3ProviderGuidPattern()
    guidPos = InStrRev(rawData, guidPattern, markerPos, vbBinaryCompare)
    If guidPos > 0 Then EventQpcForMarker = ExtractEventQpc(rawData, guidPos)
End Function

Function CalculateEtlIntervalMinutes(ByVal rawData, ByVal previousMarkerPos, ByVal latestMarkerPos)
    Dim previousQpc
    Dim latestQpc

    CalculateEtlIntervalMinutes = 0
    If previousMarkerPos <= 0 Or latestMarkerPos <= 0 Then Exit Function

    previousQpc = EventQpcForMarker(rawData, previousMarkerPos)
    latestQpc = EventQpcForMarker(rawData, latestMarkerPos)

    If previousQpc <= 0 Or latestQpc <= previousQpc Then Exit Function

    CalculateEtlIntervalMinutes = (latestQpc - previousQpc) / CDbl(ETL_QPC_TICKS_PER_SECOND) / 60
End Function

Function ExtractMetric(ByVal text, ByVal metricName)
    Dim marker
    Dim pos
    Dim valueStart
    Dim valueEnd
    Dim ch

    ExtractMetric = NOT_FOUND

    marker = metricName & "="
    pos = InStr(1, text, marker, vbTextCompare)

    If pos = 0 Then
        marker = metricName & ":"
        pos = InStr(1, text, marker, vbTextCompare)
    End If

    If pos = 0 Then Exit Function

    valueStart = pos + Len(marker)

    Do While valueStart <= Len(text) And Mid(text, valueStart, 1) = " "
        valueStart = valueStart + 1
    Loop

    valueEnd = valueStart

    Do While valueEnd <= Len(text)
        ch = Mid(text, valueEnd, 1)

        If ch = " " Or ch = "," Or ch = ";" Or ch = vbTab Or ch = vbCr Or ch = vbLf Or ch = Chr(0) Then
            Exit Do
        End If

        valueEnd = valueEnd + 1
    Loop

    If valueEnd > valueStart Then
        ExtractMetric = Mid(text, valueStart, valueEnd - valueStart)
    End If
End Function

Function ExtractProcessStatus(ByVal text, ByVal processName)
    Dim marker
    Dim pos
    Dim valueStart
    Dim valueEnd

    ExtractProcessStatus = NOT_FOUND
    marker = processName & "("
    pos = InStr(1, text, marker, vbTextCompare)

    If pos = 0 Then Exit Function

    valueStart = pos + Len(marker)
    valueEnd = InStr(valueStart, text, ")", vbTextCompare)

    If valueEnd > valueStart Then
        ExtractProcessStatus = Mid(text, valueStart, valueEnd - valueStart)
    End If
End Function

Function ExtractSectionNumericMetric(ByVal text, ByVal sectionMarker, ByVal nextSectionMarker, ByVal metricName)
    Dim sectionStart
    Dim sectionEnd
    Dim sectionText

    ExtractSectionNumericMetric = ""
    sectionStart = InStr(1, text, sectionMarker, vbTextCompare)

    If sectionStart = 0 Then Exit Function

    sectionStart = sectionStart + Len(sectionMarker)
    sectionEnd = 0

    If nextSectionMarker <> "" Then
        sectionEnd = InStr(sectionStart, text, nextSectionMarker, vbTextCompare)
    End If

    If sectionEnd > sectionStart Then
        sectionText = Mid(text, sectionStart, sectionEnd - sectionStart)
    Else
        sectionText = Mid(text, sectionStart, 300)
    End If

    ExtractSectionNumericMetric = ExtractNumericMetric(sectionText, metricName)
End Function

Function CalculateAverageMetric(ByVal totalValue, ByVal countValue)
    Dim totalNumber
    Dim countNumber

    CalculateAverageMetric = NOT_FOUND

    If Not TryParseMetricNumber(totalValue, totalNumber) Then Exit Function
    If Not TryParseMetricNumber(countValue, countNumber) Then Exit Function
    If countNumber <= 0 Then Exit Function

    CalculateAverageMetric = FormatMetricNumber(totalNumber / countNumber)
End Function

Function ConvertRunToMinutes(ByVal runValue)
    Dim parts
    Dim hoursValue
    Dim minutesValue
    Dim secondsValue

    ConvertRunToMinutes = NOT_FOUND
    If runValue = "" Or runValue = NOT_FOUND Then Exit Function

    parts = Split(CStr(runValue), ":")
    If UBound(parts) <> 2 Then Exit Function

    If Not TryParseMetricNumber(parts(0), hoursValue) Then Exit Function
    If Not TryParseMetricNumber(parts(1), minutesValue) Then Exit Function
    If Not TryParseMetricNumber(parts(2), secondsValue) Then Exit Function

    If hoursValue < 0 Then Exit Function
    If minutesValue < 0 Or minutesValue >= 60 Then Exit Function
    If secondsValue < 0 Or secondsValue >= 60 Then Exit Function

    ConvertRunToMinutes = CStr(Fix((hoursValue * 60) + minutesValue + (secondsValue / 60)))
End Function

Function CalculateErrorsPerMinute(ByVal latestScriptsText, ByVal previousScriptsText)
    Dim latestErrors
    Dim previousErrors
    Dim latestNumber
    Dim previousNumber
    Dim errorDelta

    CalculateErrorsPerMinute = NOT_FOUND
    latestErrors = ExtractNumericMetric(latestScriptsText, "Errors")
    previousErrors = ExtractNumericMetric(previousScriptsText, "Errors")

    If Not TryParseMetricNumber(latestErrors, latestNumber) Then Exit Function
    If Not TryParseMetricNumber(previousErrors, previousNumber) Then Exit Function

    If latestNumber >= previousNumber Then
        errorDelta = latestNumber - previousNumber
    Else
        Exit Function
    End If

    CalculateErrorsPerMinute = FormatWholeNumber(errorDelta)
End Function

Sub UpdateLinkMetricsFromLog(ByVal latestText, ByVal previousText, ByVal elapsedMinutes)
    Dim previousLocalQueued
    Dim previousLocalHandled
    Dim previousLocalPending
    Dim previousLocalDiscarded
    Dim previousRemoteQueued
    Dim previousRemoteHandled
    Dim previousRemotePending
    Dim previousRemoteDiscarded
    Dim resetDetected
    Dim totalQueuedDelta
    Dim totalHandledDelta
    Dim totalPendingDelta
    Dim totalDiscardedDelta

    ResetLinkIntervalOutputs

    If previousText = "" Or elapsedMinutes <= 0 Then Exit Sub

    linkEventsIntervalMinutes = FormatMetricNumber(elapsedMinutes)
    linkEventsIntervalAvailable = "1"

    previousLocalQueued = ExtractSectionNumericMetric(previousText, "Local:", "Remote:", "Queued")
    previousLocalHandled = ExtractSectionNumericMetric(previousText, "Local:", "Remote:", "Handled")
    previousLocalDiscarded = ExtractSectionNumericMetric(previousText, "Local:", "Remote:", "Discarded")
    previousLocalPending = ExtractSectionNumericMetric(previousText, "Local:", "Remote:", "Pending")
    previousRemoteQueued = ExtractSectionNumericMetric(previousText, "Remote:", "", "Queued")
    previousRemoteHandled = ExtractSectionNumericMetric(previousText, "Remote:", "", "Handled")
    previousRemoteDiscarded = ExtractSectionNumericMetric(previousText, "Remote:", "", "Discarded")
    previousRemotePending = ExtractSectionNumericMetric(previousText, "Remote:", "", "Pending")

    resetDetected = False
    runLocalQueuedDelta = CalculateCounterDelta(runLocalQueued, previousLocalQueued, resetDetected)
    runLocalHandledDelta = CalculateCounterDelta(runLocalHandled, previousLocalHandled, resetDetected)
    runLocalDiscardedDelta = CalculateCounterDelta(runLocalDiscarded, previousLocalDiscarded, resetDetected)
    runLocalPendingDelta = CalculateGaugeDelta(runLocalPending, previousLocalPending)
    If resetDetected Then runLocalCountersReset = "1"

    resetDetected = False
    runRemoteQueuedDelta = CalculateCounterDelta(runRemoteQueued, previousRemoteQueued, resetDetected)
    runRemoteHandledDelta = CalculateCounterDelta(runRemoteHandled, previousRemoteHandled, resetDetected)
    runRemoteDiscardedDelta = CalculateCounterDelta(runRemoteDiscarded, previousRemoteDiscarded, resetDetected)
    runRemotePendingDelta = CalculateGaugeDelta(runRemotePending, previousRemotePending)
    If resetDetected Then runRemoteCountersReset = "1"

    runLocalQueuedPerMinute = RateFromDelta(runLocalQueuedDelta, elapsedMinutes)
    runLocalHandledPerMinute = RateFromDelta(runLocalHandledDelta, elapsedMinutes)
    runLocalDiscardedPerMinute = RateFromDelta(runLocalDiscardedDelta, elapsedMinutes)
    runLocalPendingPerMinute = RateFromDelta(runLocalPendingDelta, elapsedMinutes)
    runRemoteQueuedPerMinute = RateFromDelta(runRemoteQueuedDelta, elapsedMinutes)
    runRemoteHandledPerMinute = RateFromDelta(runRemoteHandledDelta, elapsedMinutes)
    runRemoteDiscardedPerMinute = RateFromDelta(runRemoteDiscardedDelta, elapsedMinutes)
    runRemotePendingPerMinute = RateFromDelta(runRemotePendingDelta, elapsedMinutes)

    runLocalQueueGrowthPerMinute = SubtractMetricValues(runLocalQueuedPerMinute, runLocalHandledPerMinute)
    runRemoteQueueGrowthPerMinute = SubtractMetricValues(runRemoteQueuedPerMinute, runRemoteHandledPerMinute)
    runLocalDiscardPercent = PercentageFromDeltas(runLocalDiscardedDelta, runLocalQueuedDelta)
    runRemoteDiscardPercent = PercentageFromDeltas(runRemoteDiscardedDelta, runRemoteQueuedDelta)

    totalQueuedDelta = AddMetricValues(runLocalQueuedDelta, runRemoteQueuedDelta)
    totalHandledDelta = AddMetricValues(runLocalHandledDelta, runRemoteHandledDelta)
    totalPendingDelta = AddMetricValues(runLocalPendingDelta, runRemotePendingDelta)
    totalDiscardedDelta = AddMetricValues(runLocalDiscardedDelta, runRemoteDiscardedDelta)

    runQueuedPerMinute = RateFromDelta(totalQueuedDelta, elapsedMinutes)
    runHandledPerMinute = RateFromDelta(totalHandledDelta, elapsedMinutes)
    deltaRunPendingPerMinute = RateFromDelta(totalPendingDelta, elapsedMinutes)
    deltaRunDiscardedPerMinute = RateFromDelta(totalDiscardedDelta, elapsedMinutes)
    runQueueGrowthPerMinute = SubtractMetricValues(runQueuedPerMinute, runHandledPerMinute)
    runDiscardPercent = PercentageFromDeltas(totalDiscardedDelta, totalQueuedDelta)
End Sub

Function CalculateCounterDelta(ByVal currentValue, ByVal previousValue, ByRef resetDetected)
    Dim currentNumber
    Dim previousNumber

    CalculateCounterDelta = NOT_FOUND
    If Not TryParseMetricNumber(currentValue, currentNumber) Then Exit Function
    If Not TryParseMetricNumber(previousValue, previousNumber) Then Exit Function

    If currentNumber < previousNumber Then
        resetDetected = True
        Exit Function
    End If

    CalculateCounterDelta = FormatMetricNumber(currentNumber - previousNumber)
End Function

Function CalculateGaugeDelta(ByVal currentValue, ByVal previousValue)
    Dim currentNumber
    Dim previousNumber

    CalculateGaugeDelta = NOT_FOUND
    If Not TryParseMetricNumber(currentValue, currentNumber) Then Exit Function
    If Not TryParseMetricNumber(previousValue, previousNumber) Then Exit Function

    CalculateGaugeDelta = FormatMetricNumber(currentNumber - previousNumber)
End Function

Function RateFromDelta(ByVal deltaValue, ByVal elapsedMinutes)
    Dim deltaNumber

    RateFromDelta = NOT_FOUND
    If elapsedMinutes <= 0 Then Exit Function
    If Not TryParseMetricNumber(deltaValue, deltaNumber) Then Exit Function

    RateFromDelta = FormatMetricNumber(deltaNumber / elapsedMinutes)
End Function

Function AddMetricValues(ByVal firstValue, ByVal secondValue)
    Dim firstNumber
    Dim secondNumber

    AddMetricValues = NOT_FOUND
    If Not TryParseMetricNumber(firstValue, firstNumber) Then Exit Function
    If Not TryParseMetricNumber(secondValue, secondNumber) Then Exit Function

    AddMetricValues = FormatMetricNumber(firstNumber + secondNumber)
End Function

Function SubtractMetricValues(ByVal firstValue, ByVal secondValue)
    Dim firstNumber
    Dim secondNumber

    SubtractMetricValues = NOT_FOUND
    If Not TryParseMetricNumber(firstValue, firstNumber) Then Exit Function
    If Not TryParseMetricNumber(secondValue, secondNumber) Then Exit Function

    SubtractMetricValues = FormatMetricNumber(firstNumber - secondNumber)
End Function

Function PercentageFromDeltas(ByVal numeratorValue, ByVal denominatorValue)
    Dim numeratorNumber
    Dim denominatorNumber

    PercentageFromDeltas = NOT_FOUND
    If Not TryParseMetricNumber(numeratorValue, numeratorNumber) Then Exit Function
    If Not TryParseMetricNumber(denominatorValue, denominatorNumber) Then Exit Function

    If denominatorNumber = 0 Then
        If numeratorNumber = 0 Then PercentageFromDeltas = "0"
        Exit Function
    End If

    PercentageFromDeltas = FormatMetricNumber((numeratorNumber / denominatorNumber) * 100)
End Function

Sub UpdateAnyCounterResetFlag()
    runAnyCounterReset = "0"

    If runRestartDetected = "1" Or runLocalCountersReset = "1" Or runRemoteCountersReset = "1" Then
        runAnyCounterReset = "1"
    End If
End Sub

Sub UpdateDerivedMetrics(ByVal currentSampleTime)
    Dim elapsedMinutes
    Dim calculatedValue
    Dim currentSignature

    If foundE3RunProcess = "1" Then
        currentSignature = runPVT & "|" & runHDL & "|" & runTRD & "|" & runPGF & "|" & runRUN

        If currentSignature <> previousRunProcessSignature Then
            elapsedMinutes = MinutesBetween(previousRunProcessTime, currentSampleTime)
            runRestartDetected = CounterDecreased(runPGF, previousRunPGF)

            If elapsedMinutes > 0 Then
                deltaRunPVTPerMinute = CalculateMetricRate(runPVT, previousRunPVT, elapsedMinutes, True)
                deltaRunHDLPerMinute = CalculateMetricRate(runHDL, previousRunHDL, elapsedMinutes, True)
                deltaRunTRDPerMinute = CalculateMetricRate(runTRD, previousRunTRD, elapsedMinutes, True)
                deltaRunPGFPerMinute = CalculateMetricRate(runPGF, previousRunPGF, elapsedMinutes, False)
            End If

            UpdatePreviousMetric previousRunPVT, runPVT
            UpdatePreviousMetric previousRunHDL, runHDL
            UpdatePreviousMetric previousRunTRD, runTRD
            UpdatePreviousMetric previousRunPGF, runPGF
            previousRunProcessTime = currentSampleTime
            previousRunProcessSignature = currentSignature
        End If
    End If

    If foundE3RunScripts = "1" Then
        currentSignature = runScriptExecs & "|" & runScriptTime & "|" & runErrors

        If currentSignature <> previousRunScriptsSignature Then
            elapsedMinutes = MinutesBetween(previousRunScriptsTime, currentSampleTime)

            If elapsedMinutes > 0 Then
                calculatedValue = CalculateMetricRate(runErrors, previousRunErrors, elapsedMinutes, False)
                deltaRunErrorsPerMinute = calculatedValue
                If calculatedValue <> NOT_FOUND Then runErrorsPerMinute = calculatedValue
            End If

            UpdatePreviousMetric previousRunErrors, runErrors
            previousRunScriptsTime = currentSampleTime
            previousRunScriptsSignature = currentSignature
        End If
    End If

End Sub

Function MinutesBetween(ByVal previousTime, ByVal currentTime)
    Dim elapsedSeconds

    MinutesBetween = 0
    If IsEmpty(previousTime) Then Exit Function

    elapsedSeconds = DateDiff("s", previousTime, currentTime)
    If elapsedSeconds > 0 Then MinutesBetween = CDbl(elapsedSeconds) / 60
End Function

Sub UpdatePreviousMetric(ByRef previousValue, ByVal currentValue)
    If currentValue <> "" And currentValue <> NOT_FOUND Then previousValue = currentValue
End Sub

Function CalculateMetricRate(ByVal currentValue, ByVal previousValue, ByVal elapsedMinutes, ByVal allowNegative)
    Dim currentNumber
    Dim previousNumber
    Dim difference

    CalculateMetricRate = NOT_FOUND

    If elapsedMinutes <= 0 Then Exit Function
    If Not TryParseMetricNumber(currentValue, currentNumber) Then Exit Function
    If Not TryParseMetricNumber(previousValue, previousNumber) Then Exit Function

    difference = currentNumber - previousNumber
    If Not allowNegative And difference < 0 Then Exit Function

    CalculateMetricRate = FormatMetricNumber(difference / elapsedMinutes)
End Function

Function CounterDecreased(ByVal currentValue, ByVal previousValue)
    Dim currentNumber
    Dim previousNumber

    CounterDecreased = "0"
    If Not TryParseMetricNumber(currentValue, currentNumber) Then Exit Function
    If Not TryParseMetricNumber(previousValue, previousNumber) Then Exit Function

    If currentNumber < previousNumber Then CounterDecreased = "1"
End Function

Function TryParseMetricNumber(ByVal value, ByRef numberValue)
    Dim normalized
    Dim decimalSeparator

    On Error Resume Next

    TryParseMetricNumber = False
    If IsEmpty(value) Or IsNull(value) Then Exit Function
    If CStr(value) = "" Or CStr(value) = NOT_FOUND Then Exit Function

    normalized = CStr(value)
    decimalSeparator = Mid(CStr(1.5), 2, 1)

    If decimalSeparator = "," Then
        normalized = Replace(normalized, ".", ",")
    Else
        normalized = Replace(normalized, ",", ".")
    End If

    Err.Clear
    numberValue = CDbl(normalized)

    If Err.Number = 0 Then TryParseMetricNumber = True
    Err.Clear
End Function

Function FormatMetricNumber(ByVal value)
    Dim result

    result = CStr(Round(value, 3))
    If Mid(CStr(1.5), 2, 1) = "," Then result = Replace(result, ",", ".")
    FormatMetricNumber = result
End Function

Function ExtractNumericMetric(ByVal text, ByVal metricName)
    Dim value

    ExtractNumericMetric = ""
    value = ExtractMetric(text, metricName)

    If value = NOT_FOUND Then Exit Function

    ExtractNumericMetric = ExtractLeadingNumber(value)
End Function

Function ExtractLeadingNumber(ByVal value)
    Dim i
    Dim ch
    Dim result

    result = ""

    For i = 1 To Len(value)
        ch = Mid(value, i, 1)

        If (ch >= "0" And ch <= "9") Or ch = "." Or ch = "," Or ch = "-" Then
            result = result & ch
        Else
            Exit For
        End If
    Next

    ExtractLeadingNumber = result
End Function

Function SumMetricValues(ByVal text, ByVal metricName, ByVal maxOccurrences)
    Dim marker
    Dim pos
    Dim valueStart
    Dim valueEnd
    Dim ch
    Dim valueText
    Dim numberText
    Dim numberValue
    Dim total
    Dim found
    Dim count

    SumMetricValues = NOT_FOUND
    marker = metricName & "="
    pos = 1
    total = 0
    found = False
    count = 0

    Do
        pos = InStr(pos, text, marker, vbTextCompare)
        If pos = 0 Then Exit Do

        valueStart = pos + Len(marker)

        Do While valueStart <= Len(text) And Mid(text, valueStart, 1) = " "
            valueStart = valueStart + 1
        Loop

        valueEnd = valueStart

        Do While valueEnd <= Len(text)
            ch = Mid(text, valueEnd, 1)

            If ch = " " Or ch = "," Or ch = ";" Or ch = vbTab Or ch = vbCr Or ch = vbLf Or ch = Chr(0) Then
                Exit Do
            End If

            valueEnd = valueEnd + 1
        Loop

        If valueEnd > valueStart Then
            valueText = Mid(text, valueStart, valueEnd - valueStart)
            numberText = ExtractLeadingNumber(valueText)

            If TryParseMetricNumber(numberText, numberValue) Then
                total = total + numberValue
                found = True
                count = count + 1
            End If
        End If

        If maxOccurrences > 0 And count >= maxOccurrences Then Exit Do

        pos = valueEnd + 1
    Loop

    If found Then
        SumMetricValues = FormatWholeNumber(total)
    End If
End Function

Function FormatWholeNumber(ByVal value)
    If value = Fix(value) Then
        FormatWholeNumber = CStr(Fix(value))
    Else
        FormatWholeNumber = FormatMetricNumber(value)
    End If
End Function

Sub OnRead_runCPU(r, v)
    v.Value = runCPU
End Sub

Sub OnRead_runPVT(r, v)
    v.Value = runPVT
End Sub

Sub OnRead_runHDL(r, v)
    v.Value = runHDL
End Sub

Sub OnRead_runTRD(r, v)
    v.Value = runTRD
End Sub

Sub OnRead_runUptimeMinutes(r, v)
    v.Value = runUptimeMinutes
End Sub

Sub OnRead_runRestartDetected(r, v)
    v.Value = runRestartDetected
End Sub

Sub OnRead_runOccupancy(r, v)
    v.Value = runOccupancy
End Sub

Sub OnRead_runAvgScriptTime(r, v)
    v.Value = runAvgScriptTime
End Sub

Sub OnRead_runErrorsPerMinute(r, v)
    v.Value = runErrorsPerMinute
End Sub

Sub OnRead_runMemory(r, v)
    v.Value = runMemory
End Sub

Sub OnRead_runPageFaults(r, v)
    v.Value = runPageFaults
End Sub

Sub OnRead_runLocalPending(r, v)
    v.Value = runLocalPending
End Sub

Sub OnRead_runRemotePending(r, v)
    v.Value = runRemotePending
End Sub

Sub OnRead_runLocalQueuedPerMinute(r, v)
    v.Value = runLocalQueuedPerMinute
End Sub

Sub OnRead_runLocalHandledPerMinute(r, v)
    v.Value = runLocalHandledPerMinute
End Sub

Sub OnRead_runLocalDiscardedPerMinute(r, v)
    v.Value = runLocalDiscardedPerMinute
End Sub

Sub OnRead_runRemoteQueuedPerMinute(r, v)
    v.Value = runRemoteQueuedPerMinute
End Sub

Sub OnRead_runRemoteHandledPerMinute(r, v)
    v.Value = runRemoteHandledPerMinute
End Sub

Sub OnRead_runRemoteDiscardedPerMinute(r, v)
    v.Value = runRemoteDiscardedPerMinute
End Sub

Sub OnRead_runLocalQueueGrowthPerMinute(r, v)
    v.Value = runLocalQueueGrowthPerMinute
End Sub

Sub OnRead_runRemoteQueueGrowthPerMinute(r, v)
    v.Value = runRemoteQueueGrowthPerMinute
End Sub

Sub OnRead_runLocalDiscardPercent(r, v)
    v.Value = runLocalDiscardPercent
End Sub

Sub OnRead_runRemoteDiscardPercent(r, v)
    v.Value = runRemoteDiscardPercent
End Sub

Sub OnRead_linkEventsIntervalMinutes(r, v)
    v.Value = linkEventsIntervalMinutes
End Sub

Sub OnRead_linkEventsIntervalAvailable(r, v)
    v.Value = linkEventsIntervalAvailable
End Sub

Sub OnRead_runAnyCounterReset(r, v)
    v.Value = runAnyCounterReset
End Sub

Sub OnRead_globalCPU(r, v)
    v.Value = globalCPU
End Sub

Sub OnRead_globalThreads(r, v)
    v.Value = globalThreads
End Sub

Sub OnRead_driveCFreeMB(r, v)
    v.Value = driveCFreeMB
End Sub

Sub OnRead_ioQueuePending(r, v)
    v.Value = ioQueuePending
End Sub

Sub OnRead_ioQueueAvgDelay(r, v)
    v.Value = ioQueueAvgDelay
End Sub

Sub OnRead_serverStatus(r, v)
    v.Value = serverStatus
End Sub

Sub OnRead_serverCPU(r, v)
    v.Value = serverCPU
End Sub

Sub OnRead_serverPVT(r, v)
    v.Value = serverPVT
End Sub

Sub OnRead_serverHDL(r, v)
    v.Value = serverHDL
End Sub

Sub OnRead_collectionTimestamp(r, v)
    v.Value = collectionTimestamp
End Sub

Sub OnRead_sampleAgeSeconds(r, v)
    v.Value = sampleAgeSeconds
End Sub

Sub OnRead_etlFileSizeMB(r, v)
    v.Value = etlFileSizeMB
End Sub

Sub OnRead_etlFileChanged(r, v)
    v.Value = etlFileChanged
End Sub

Sub OnRead_foundProcessSummary(r, v)
    v.Value = foundProcessSummary
End Sub

Sub OnRead_foundE3RunProcess(r, v)
    v.Value = foundE3RunProcess
End Sub

Sub OnRead_foundE3RunScripts(r, v)
    v.Value = foundE3RunScripts
End Sub

Sub OnRead_foundE3RunLinkEvents(r, v)
    v.Value = foundE3RunLinkEvents
End Sub

Sub OnRead_foundIOQueue(r, v)
    v.Value = foundIOQueue
End Sub

Sub OnRead_foundE3Server(r, v)
    v.Value = foundE3Server
End Sub

Sub OnRead_status(r, v)
    v.Value = statusGlobal
End Sub

Sub OnRead_totalTime(r, v)
    v.Value = totalTime
End Sub

Sub OnRead(r, v)
    v.Value = "ParamItem sem funcao OnRead especifica: " & r.ParamItem
    v.Quality = BAD_QUALITY
End Sub


