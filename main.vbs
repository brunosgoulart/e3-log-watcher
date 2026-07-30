'Version 2.0.0 - 2026-07-30

Option Explicit

Const ETL_SOURCE_FOLDER = "F:\eeLogs\E3"
Const LOG_FILE_PREFIX = "E3_"
Const INITIAL_TAIL_READ_MB = 1
Const TAIL_READ_STEP_MB = 1
Const MAX_TAIL_READ_MB = 1
Const MAX_TEXT_AFTER_MARKER = 2500
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
Dim etlSizeGlobal
Dim etlModifiedGlobal
Dim incrementRequestedGlobal
Dim incrementReceivedGlobal
Dim rollingBufferCharsGlobal

Dim runCPU
Dim runPVT
Dim runHDL
Dim runTRD
Dim runOccupancy
Dim runPendingEvents
Dim runDiscardedEvents
Dim runErrors
Dim runErrorsPerMinute
Dim runAvgScriptTime
Dim runRemoteDiscardedPerMinute
Dim runRemoteDiscardPercent
Dim runRemoteHandledPerMinute
Dim runRemotePending
Dim runUptimeMinutes
Dim runMemory
Dim runPageFaults
Dim ioQueueAvgDelay
Dim ioQueuePending
Dim serverStatus
Dim serverCPU
Dim serverHDL
Dim serverPVT
Dim statusGlobal
Dim statusMsgGlobal
Dim fileRead
Dim totalTime
Dim readModeGlobal
Dim collectionTimestamp
Dim previousRunErrors
Dim previousRunErrorsTime


Sub OnStart()
    ResetOutputs "Aguardando leitura do trigger"
    ResetErrorRateState

    Err.Clear
    Set fsoGlobal = CreateObject("Scripting.FileSystemObject")

    If Err.Number <> 0 Then
        statusGlobal = "Fail"
        statusMsgGlobal = "Erro criando FileSystemObject: " & Err.Description
        Err.Clear
    End If
End Sub

Sub ResetErrorRateState()
    previousRunErrors = NOT_FOUND
    previousRunErrorsTime = Empty
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
    runOccupancy = NOT_FOUND
    runPendingEvents = NOT_FOUND
    runDiscardedEvents = NOT_FOUND
    runErrors = NOT_FOUND
    runErrorsPerMinute = NOT_FOUND
    runAvgScriptTime = NOT_FOUND
    runRemoteDiscardedPerMinute = NOT_FOUND
    runRemoteDiscardPercent = NOT_FOUND
    runRemoteHandledPerMinute = NOT_FOUND
    runRemotePending = NOT_FOUND
    runUptimeMinutes = NOT_FOUND
    runMemory = NOT_FOUND
    runPageFaults = NOT_FOUND
    ioQueueAvgDelay = NOT_FOUND
    ioQueuePending = NOT_FOUND

    serverStatus = NOT_FOUND
    serverCPU = NOT_FOUND
    serverHDL = NOT_FOUND
    serverPVT = NOT_FOUND

    statusGlobal = "Idle"
    statusMsgGlobal = msg
    fileRead = ""
    totalTime = ""
    readModeGlobal = ""
    collectionTimestamp = ""
    etlSizeGlobal = ""
    etlModifiedGlobal = ""
    incrementRequestedGlobal = ""
    incrementReceivedGlobal = ""
    rollingBufferCharsGlobal = ""
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
    Dim currentSampleTime
    Dim runText
    Dim currentErrors
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

    scriptStartTime = Timer
    statusMsg = "OK"

    If EnsureFileSystem(statusMsg) Then

        If FindLatestEtl(latestPath, latestSize, statusMsg) Then

            fileRead = latestPath

            If ReadAdaptiveTail(latestPath, latestSize, processSummaryText, e3RunProcessText, e3RunScriptsText, e3RunPreviousScriptsText, e3RunLinkEventsText, e3RunPreviousLinkEventsText, linkInterval, ioQueueText, e3ServerText, tailUsedMb, statusMsg) Then

                If processSummaryText <> "" Then
                    UpdateValueIfFound runMemory, ExtractNumericMetric(processSummaryText, "MemoryLoad")
                    UpdateValueIfFound runPageFaults, ExtractNumericMetric(processSummaryText, "PageFaults")
                    UpdateValueIfFound serverStatus, ExtractProcessStatus(processSummaryText, "E3Server")
                End If

                If e3RunProcessText <> "" Then
                    UpdateValueIfFound runCPU, ExtractNumericMetric(e3RunProcessText, "CPU")
                    UpdateValueIfFound runPVT, ExtractNumericMetric(e3RunProcessText, "PVT")
                    UpdateValueIfFound runHDL, ExtractNumericMetric(e3RunProcessText, "HDL")
                    UpdateValueIfFound runTRD, ExtractNumericMetric(e3RunProcessText, "TRD")
                    runText = ExtractMetric(e3RunProcessText, "RUN")
                    UpdateValueIfFound runUptimeMinutes, ConvertRunToMinutes(runText)
                End If

                If e3RunScriptsText <> "" Then
                    UpdateValueIfFound runOccupancy, ExtractNumericMetric(e3RunScriptsText, "Occupancy")
                    currentErrors = ExtractNumericMetric(e3RunScriptsText, "Errors")
                    UpdateValueIfFound runErrors, currentErrors
                    runErrorsPerMinute = CalculateErrorsPerMinute(currentErrors, currentSampleTime)
                    UpdateValueIfFound runAvgScriptTime, CalculateAverageMetric(ExtractNumericMetric(e3RunScriptsText, "Time"), ExtractNumericMetric(e3RunScriptsText, "Execs"))
                End If

                If e3RunLinkEventsText <> "" Then
                    UpdateValueIfFound runPendingEvents, SumMetricValues(e3RunLinkEventsText, "Pending", 2)
                    UpdateValueIfFound runDiscardedEvents, SumMetricValues(e3RunLinkEventsText, "Discarded", 2)
                    UpdateValueIfFound runRemotePending, ExtractSectionNumericMetric(e3RunLinkEventsText, "Remote:", "", "Pending")
                    UpdateValueIfFound runRemoteDiscardedPerMinute, CalculateSectionMetricPerMinute(e3RunLinkEventsText, e3RunPreviousLinkEventsText, linkInterval, "Remote:", "", "Discarded")
                    UpdateValueIfFound runRemoteHandledPerMinute, CalculateSectionMetricPerMinute(e3RunLinkEventsText, e3RunPreviousLinkEventsText, linkInterval, "Remote:", "", "Handled")
                    UpdateValueIfFound runRemoteDiscardPercent, CalculateRemoteDiscardPercent(e3RunLinkEventsText, e3RunPreviousLinkEventsText)
                End If

                If ioQueueText <> "" Then
                    UpdateValueIfFound ioQueuePending, ExtractNumericMetric(ioQueueText, "Pending")
                    UpdateValueIfFound ioQueueAvgDelay, ExtractNumericMetric(ioQueueText, "AvgDelay")
                End If

                If e3ServerText <> "" Then
                    If serverStatus = NOT_FOUND Then serverStatus = "1"
                    UpdateValueIfFound serverCPU, ExtractNumericMetric(e3ServerText, "CPU")
                    UpdateValueIfFound serverPVT, ExtractNumericMetric(e3ServerText, "PVT")
                    UpdateValueIfFound serverHDL, ExtractNumericMetric(e3ServerText, "HDL")
                End If

                statusGlobal = "Success"
                statusMsgGlobal = "Leitura concluida; tail=" & CStr(tailUsedMb) & " MB; modo=" & readModeGlobal & "; inc=" & incrementReceivedGlobal & "/" & incrementRequestedGlobal & "; buffer=" & rollingBufferCharsGlobal

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

    totalTime = CStr(Round(scriptElapsedSeconds, 3))

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

Function FindLatestEtl(ByRef latestPath, ByRef latestSize, ByRef statusMsg)
    Dim folder
    Dim file
    Dim fileName
    Dim latestDate

    FindLatestEtl = False
    latestPath = ""
    latestSize = 0
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
                End If
            End If
        End If
    Next

    If latestPath = "" Then
        statusMsg = "Nenhum ETL encontrado em " & ETL_SOURCE_FOLDER & " com prefixo " & LOG_FILE_PREFIX
        Exit Function
    End If

    etlSizeGlobal = CStr(latestSize)
    etlModifiedGlobal = FormatDateTimeIso(latestDate)
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
    incrementRequestedGlobal = ""
    incrementReceivedGlobal = ""
    rollingBufferCharsGlobal = ""

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

        SetReadDiagnostic tailBytes, Len(rollingTailTextGlobal)
        If Len(rollingTailTextGlobal) <> tailBytes Then readModeGlobal = "inc-open-partial"
        rawData = rollingTailTextGlobal
        ReadTailWindowIncremental = True
        Exit Function
    End If

    If StrComp(tailFilePathGlobal, latestPath, vbTextCompare) <> 0 Or latestSize < tailFileSizeGlobal Then
        CloseTailStream

        If Not OpenIncrementalTailStream(latestPath, latestSize, tailBytes, statusMsg) Then
            Exit Function
        End If

        SetReadDiagnostic tailBytes, Len(rollingTailTextGlobal)
        If Len(rollingTailTextGlobal) <> tailBytes Then
            readModeGlobal = "inc-reopen-partial"
        Else
            readModeGlobal = "inc-reopen"
        End If
        rawData = rollingTailTextGlobal
        ReadTailWindowIncremental = True
        Exit Function
    End If

    newBytes = latestSize - tailFileSizeGlobal

    If newBytes > 0 Then
        readModeGlobal = "inc-read"
        SetReadDiagnostic newBytes, 0
        Err.Clear
        newData = tailStreamGlobal.Read(CLng(newBytes))

        If Err.Number <> 0 Then
            statusMsg = "Erro lendo incremento do ETL: " & Err.Description
            Err.Clear
            Exit Function
        End If

        SetReadDiagnostic newBytes, Len(newData)
        If Len(newData) <> newBytes Then readModeGlobal = "inc-read-partial"

        If Len(newData) > 0 Then
            rollingTailTextGlobal = rollingTailTextGlobal & newData
            TrimRollingTailBuffer
        End If

        tailFileSizeGlobal = latestSize
    Else
        readModeGlobal = "inc-cache"
        SetReadDiagnostic 0, 0
    End If

    rollingBufferCharsGlobal = CStr(Len(rollingTailTextGlobal))
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

    SetReadDiagnostic tailBytes, Len(rawData)
    rollingBufferCharsGlobal = CStr(Len(rawData))
    If Len(rawData) <> tailBytes Then readModeGlobal = "fallback-text-partial"

    ts.Close
    ReadTailWindowWithTextStream = True
End Function

Sub TrimRollingTailBuffer()
    If Len(rollingTailTextGlobal) > ROLLING_BUFFER_MAX_CHARS Then
        rollingTailTextGlobal = Right(rollingTailTextGlobal, ROLLING_BUFFER_MAX_CHARS)
    End If
End Sub

Sub SetReadDiagnostic(ByVal requestedAmount, ByVal receivedAmount)
    incrementRequestedGlobal = CStr(requestedAmount)
    incrementReceivedGlobal = CStr(receivedAmount)
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

Function CalculateErrorsPerMinute(ByVal currentErrors, ByVal currentSampleTime)
    Dim currentErrorsNumber
    Dim previousErrorsNumber
    Dim elapsedSeconds
    Dim elapsedMinutes

    CalculateErrorsPerMinute = NOT_FOUND
    If Not TryParseMetricNumber(currentErrors, currentErrorsNumber) Then Exit Function

    If IsEmpty(previousRunErrorsTime) Or Not TryParseMetricNumber(previousRunErrors, previousErrorsNumber) Then
        previousRunErrors = currentErrors
        previousRunErrorsTime = currentSampleTime
        Exit Function
    End If

    elapsedSeconds = DateDiff("s", previousRunErrorsTime, currentSampleTime)

    If elapsedSeconds > 0 And currentErrorsNumber >= previousErrorsNumber Then
        elapsedMinutes = CDbl(elapsedSeconds) / 60
        CalculateErrorsPerMinute = FormatMetricNumber((currentErrorsNumber - previousErrorsNumber) / elapsedMinutes)
    End If

    previousRunErrors = currentErrors
    previousRunErrorsTime = currentSampleTime
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
    If UBound(parts) = 1 Then
        hoursValue = 0
        If Not TryParseMetricNumber(parts(0), minutesValue) Then Exit Function
        If Not TryParseMetricNumber(parts(1), secondsValue) Then Exit Function
    ElseIf UBound(parts) = 2 Then
        If Not TryParseMetricNumber(parts(0), hoursValue) Then Exit Function
        If Not TryParseMetricNumber(parts(1), minutesValue) Then Exit Function
        If Not TryParseMetricNumber(parts(2), secondsValue) Then Exit Function
    Else
        Exit Function
    End If

    If hoursValue < 0 Or minutesValue < 0 Then Exit Function
    If UBound(parts) = 2 And minutesValue >= 60 Then Exit Function
    If secondsValue < 0 Or secondsValue >= 60 Then Exit Function

    ConvertRunToMinutes = CStr(Fix((hoursValue * 60) + minutesValue + (secondsValue / 60)))
End Function

Function CalculateSectionMetricPerMinute(ByVal latestText, ByVal previousText, ByVal elapsedMinutes, ByVal sectionMarker, ByVal nextSectionMarker, ByVal metricName)
    Dim latestValue
    Dim previousValue
    Dim latestNumber
    Dim previousNumber

    CalculateSectionMetricPerMinute = NOT_FOUND
    If elapsedMinutes <= 0 Then Exit Function

    latestValue = ExtractSectionNumericMetric(latestText, sectionMarker, nextSectionMarker, metricName)
    previousValue = ExtractSectionNumericMetric(previousText, sectionMarker, nextSectionMarker, metricName)

    If Not TryParseMetricNumber(latestValue, latestNumber) Then Exit Function
    If Not TryParseMetricNumber(previousValue, previousNumber) Then Exit Function
    If latestNumber < previousNumber Then Exit Function

    CalculateSectionMetricPerMinute = FormatMetricNumber((latestNumber - previousNumber) / elapsedMinutes)
End Function

Function CalculateRemoteDiscardPercent(ByVal latestText, ByVal previousText)
    Dim latestDiscarded
    Dim previousDiscarded
    Dim latestQueued
    Dim previousQueued
    Dim latestDiscardedNumber
    Dim previousDiscardedNumber
    Dim latestQueuedNumber
    Dim previousQueuedNumber
    Dim discardedDelta
    Dim queuedDelta

    CalculateRemoteDiscardPercent = NOT_FOUND

    latestDiscarded = ExtractSectionNumericMetric(latestText, "Remote:", "", "Discarded")
    previousDiscarded = ExtractSectionNumericMetric(previousText, "Remote:", "", "Discarded")
    latestQueued = ExtractSectionNumericMetric(latestText, "Remote:", "", "Queued")
    previousQueued = ExtractSectionNumericMetric(previousText, "Remote:", "", "Queued")

    If Not TryParseMetricNumber(latestDiscarded, latestDiscardedNumber) Then Exit Function
    If Not TryParseMetricNumber(previousDiscarded, previousDiscardedNumber) Then Exit Function
    If Not TryParseMetricNumber(latestQueued, latestQueuedNumber) Then Exit Function
    If Not TryParseMetricNumber(previousQueued, previousQueuedNumber) Then Exit Function

    discardedDelta = latestDiscardedNumber - previousDiscardedNumber
    queuedDelta = latestQueuedNumber - previousQueuedNumber
    If discardedDelta < 0 Or queuedDelta < 0 Then Exit Function

    If queuedDelta = 0 Then
        If discardedDelta = 0 Then CalculateRemoteDiscardPercent = "0"
        Exit Function
    End If

    CalculateRemoteDiscardPercent = FormatMetricNumber((discardedDelta / queuedDelta) * 100)
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

Function FormatDateTimeIso(ByVal value)
    FormatDateTimeIso = CStr(Year(value)) & "-" & Pad2(Month(value)) & "-" & Pad2(Day(value)) & " " & Pad2(Hour(value)) & ":" & Pad2(Minute(value)) & ":" & Pad2(Second(value))
End Function

Function Pad2(ByVal value)
    Pad2 = Right("0" & CStr(value), 2)
End Function

Function SumMetricValues(ByVal text, ByVal metricName, ByVal maxOccurrences)
    Dim marker
    Dim pos
    Dim valueStart
    Dim valueEnd
    Dim ch
    Dim valueText
    Dim numberText
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

            If numberText <> "" Then
                total = total + CDbl(numberText)
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
        FormatWholeNumber = CStr(Round(value, 3))
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

Sub OnRead_runOccupancy(r, v)
    v.Value = runOccupancy
End Sub

Sub OnRead_runPendingEvents(r, v)
    v.Value = runPendingEvents
End Sub

Sub OnRead_runDiscardedEvents(r, v)

    v.Value = runDiscardedEvents

End Sub



Sub OnRead_runErrors(r, v)

    v.Value = runErrors

End Sub



Sub OnRead_runErrorsPerMinute(r, v)

    v.Value = runErrorsPerMinute

End Sub

Sub OnRead_runAvgScriptTime(r, v)
    v.Value = runAvgScriptTime
End Sub

Sub OnRead_runRemotePending(r, v)
    v.Value = runRemotePending
End Sub

Sub OnRead_runRemoteDiscardedPerMinute(r, v)
    v.Value = runRemoteDiscardedPerMinute
End Sub

Sub OnRead_runRemoteHandledPerMinute(r, v)
    v.Value = runRemoteHandledPerMinute
End Sub

Sub OnRead_runRemoteDiscardPercent(r, v)
    v.Value = runRemoteDiscardPercent
End Sub


Sub OnRead_runMemory(r, v)
    v.Value = runMemory
End Sub

Sub OnRead_runPageFaults(r, v)
    v.Value = runPageFaults
End Sub

Sub OnRead_ioQueuePending(r, v)
    v.Value = ioQueuePending
End Sub

Sub OnRead_ioQueueAvgDelay(r, v)
    v.Value = ioQueueAvgDelay
End Sub

Sub OnRead_serverCPU(r, v)
    v.Value = serverCPU
End Sub

Sub OnRead_serverStatus(r, v)
    v.Value = serverStatus
End Sub

Sub OnRead_serverHDL(r, v)
    v.Value = serverHDL
End Sub

Sub OnRead_serverPVT(r, v)
    v.Value = serverPVT
End Sub

Sub OnRead_collectionTimestamp(r, v)
    v.Value = collectionTimestamp
End Sub

Sub OnRead_readMode(r, v)
    v.Value = readModeGlobal
End Sub

Sub OnRead_etlSize(r, v)
    v.Value = etlSizeGlobal
End Sub

Sub OnRead_etlModified(r, v)
    v.Value = etlModifiedGlobal
End Sub

Sub OnRead_incrementRequested(r, v)
    v.Value = incrementRequestedGlobal
End Sub

Sub OnRead_incrementReceived(r, v)
    v.Value = incrementReceivedGlobal
End Sub

Sub OnRead_rollingBufferChars(r, v)
    v.Value = rollingBufferCharsGlobal
End Sub

Sub OnRead_status(r, v)
    v.Value = statusGlobal
End Sub

Sub OnRead_statusMsg(r, v)
    v.Value = statusMsgGlobal
End Sub

Sub OnRead_fileRead(r, v)
    v.Value = fileRead
End Sub

Sub OnRead_totalTime(r, v)
    v.Value = totalTime
End Sub

Sub OnRead(r, v)
    v.Value = "ParamItem sem funcao OnRead especifica: " & r.ParamItem
    v.Quality = BAD_QUALITY
End Sub
