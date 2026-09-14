pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qs.modules.theme
import qs.modules.components
import qs.modules.globals
import qs.config
import qs.modules.lockscreen

Item {
    id: root

    property int maxContentWidth: 480
    readonly property int contentWidth: Math.min(width, maxContentWidth)
    readonly property real sideMargin: (width - contentWidth) / 2

    property string currentSection: ""

    FingerprintEnrollWizard {
        id: enrollWizard
        anchors.centerIn: parent
        onEnrollAccepted: FingerprintService.listFingers()
    }

    component SectionButton: StyledRect {
        id: sectionBtn
        required property string text
        required property string sectionId

        property bool isHovered: false

        variant: isHovered ? "focus" : "pane"
        Layout.fillWidth: true
        Layout.preferredHeight: 56
        radius: Styling.radius(0)

        RowLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 16

            Text {
                text: sectionBtn.text
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(0)
                font.bold: true
                color: Colors.overBackground
                Layout.fillWidth: true
            }

            Text {
                text: Icons.caretRight
                font.family: Icons.font
                font.pixelSize: Styling.fontSize(6)
                color: Colors.overSurfaceVariant
            }
        }

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onEntered: sectionBtn.isHovered = true
            onExited: sectionBtn.isHovered = false
            onClicked: root.currentSection = sectionBtn.sectionId
        }
    }

    // Main content
    Flickable {
        id: mainFlickable
        anchors.fill: parent
        contentHeight: mainColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        ColumnLayout {
            id: mainColumn
            width: mainFlickable.width
            spacing: 8

            // Header wrapper
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: titlebar.height

                PanelTitlebar {
                    id: titlebar
                    width: root.contentWidth
                    anchors.horizontalCenter: parent.horizontalCenter
                    title: root.currentSection === "" ? "System" : (root.currentSection === "system" ? "System Resources" : (root.currentSection.charAt(0).toUpperCase() + root.currentSection.slice(1)))
                    statusText: ""

                    actions: {
                        if (root.currentSection !== "") {
                            return [
                                {
                                    icon: Icons.arrowLeft,
                                    tooltip: "Back",
                                    onClicked: function () {
                                        root.currentSection = "";
                                    }
                                }
                            ];
                        }
                        return [];
                    }
                }
            }

            // Content wrapper - centered
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: contentColumn.implicitHeight

                ColumnLayout {
                    id: contentColumn
                    width: root.contentWidth
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 16

                    // ═══════════════════════════════════════════════════════════════
                    // MENU SECTION
                    // ═══════════════════════════════════════════════════════════════
                    ColumnLayout {
                        visible: root.currentSection === ""
                        Layout.fillWidth: true
                        spacing: 8

                        SectionButton {
                            text: "Prefixes"
                            sectionId: "prefixes"
                        }
                        SectionButton {
                            text: "Weather"
                            sectionId: "weather"
                        }
                        SectionButton {
                            text: "Performance"
                            sectionId: "performance"
                        }
                        SectionButton {
                            text: "System Resources"
                            sectionId: "system"
                        }
                        SectionButton {
                            text: "Idle"
                            sectionId: "idle"
                        }
                        SectionButton {
                            text: "Terminal"
                            sectionId: "terminal"
                        }
                        SectionButton {
                            text: "Authentication"
                            sectionId: "authentication"
                        }
                    }

                    // =====================
                    // PREFIX SECTION
                    // =====================
                    ColumnLayout {
                        visible: root.currentSection === "prefixes"
                        property string settingsSection: "prefixes"
                        Layout.fillWidth: true
                        spacing: 8

                        Text {
                            text: "Prefixes"
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-1)
                            font.weight: Font.Medium
                            color: Colors.overSurfaceVariant
                            Layout.bottomMargin: -4
                        }

                        Text {
                            text: "Keyboard shortcuts for quick actions in launcher"
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-2)
                            color: Colors.overSurfaceVariant
                            opacity: 0.7
                        }

                        // Clipboard prefix
                        PrefixRow {
                            Layout.fillWidth: true
                            label: "Clipboard"
                            prefixValue: Config.prefix.clipboard
                            onPrefixEdited: newValue => {
                                Config.prefix.clipboard = newValue;
                            }
                        }

                        // Emoji prefix
                        PrefixRow {
                            Layout.fillWidth: true
                            label: "Emoji"
                            prefixValue: Config.prefix.emoji
                            onPrefixEdited: newValue => {
                                Config.prefix.emoji = newValue;
                            }
                        }

                        // Tmux prefix
                        PrefixRow {
                            Layout.fillWidth: true
                            label: "Tmux"
                            prefixValue: Config.prefix.tmux
                            onPrefixEdited: newValue => {
                                Config.prefix.tmux = newValue;
                            }
                        }

                        // Wallpapers prefix
                        PrefixRow {
                            Layout.fillWidth: true
                            label: "Wallpapers"
                            prefixValue: Config.prefix.wallpapers
                            onPrefixEdited: newValue => {
                                Config.prefix.wallpapers = newValue;
                            }
                        }

                        // Notes prefix
                        PrefixRow {
                            Layout.fillWidth: true
                            label: "Notes"
                            prefixValue: Config.prefix.notes
                            onPrefixEdited: newValue => {
                                Config.prefix.notes = newValue;
                            }
                        }
                    }

                    // =====================
                    // WEATHER SECTION
                    // =====================
                    ColumnLayout {
                        visible: root.currentSection === "weather"
                        property string settingsSection: "weather"
                        Layout.fillWidth: true
                        spacing: 8

                        Text {
                            text: "Weather"
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-1)
                            font.weight: Font.Medium
                            color: Colors.overSurfaceVariant
                            Layout.bottomMargin: -4
                        }

                        // Location
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Text {
                                text: "Location"
                                font.family: Config.theme.font
                                font.pixelSize: Styling.fontSize(0)
                                color: Colors.overBackground
                                Layout.preferredWidth: 100
                            }

                            StyledRect {
                                variant: "common"
                                Layout.fillWidth: true
                                Layout.preferredHeight: 36
                                radius: Styling.radius(-2)

                                TextInput {
                                    id: locationInput
                                    anchors.fill: parent
                                    anchors.margins: 8
                                    font.family: Config.theme.font
                                    font.pixelSize: Styling.fontSize(0)
                                    color: Colors.overBackground
                                    selectByMouse: true
                                    clip: true
                                    verticalAlignment: TextInput.AlignVCenter

                                    readonly property string configValue: Config.weather.location

                                    onConfigValueChanged: {
                                        if (text !== configValue) {
                                            text = configValue;
                                        }
                                    }

                                    Component.onCompleted: text = configValue

                                    onEditingFinished: {
                                        if (text !== Config.weather.location) {
                                            Config.weather.location = text.trim();
                                        }
                                    }

                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        visible: !locationInput.text && !locationInput.activeFocus
                                        text: "e.g. Buenos Aires, Tokyo..."
                                        font: locationInput.font
                                        color: Colors.overSurfaceVariant
                                    }
                                }
                            }
                        }

                        // Unit selector
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Text {
                                text: "Unit"
                                font.family: Config.theme.font
                                font.pixelSize: Styling.fontSize(0)
                                color: Colors.overBackground
                                Layout.preferredWidth: 100
                            }

                            Row {
                                spacing: 8

                                Repeater {
                                    model: [
                                        {
                                            id: "C",
                                            label: "Celsius"
                                        },
                                        {
                                            id: "F",
                                            label: "Fahrenheit"
                                        }
                                    ]

                                    delegate: StyledRect {
                                        id: unitButton
                                        required property var modelData
                                        required property int index

                                        property bool isSelected: Config.weather.unit === modelData.id
                                        property bool isHovered: false

                                        variant: isSelected ? "primary" : (isHovered ? "focus" : "common")
                                        width: unitLabel.width + 24
                                        height: 36
                                        radius: Styling.radius(-2)

                                        Text {
                                            id: unitLabel
                                            anchors.centerIn: parent
                                            text: unitButton.modelData.label
                                            font.family: Config.theme.font
                                            font.pixelSize: Styling.fontSize(0)
                                            font.weight: unitButton.isSelected ? Font.Bold : Font.Normal
                                            color: unitButton.item
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onEntered: unitButton.isHovered = true
                                            onExited: unitButton.isHovered = false
                                            onClicked: Config.weather.unit = unitButton.modelData.id
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // =====================
                    // PERFORMANCE SECTION
                    // =====================
                    ColumnLayout {
                        visible: root.currentSection === "performance"
                        property string settingsSection: "performance"
                        Layout.fillWidth: true
                        spacing: 8

                        SettingsGroup {
                            title: "Performance"
                            description: "Turn off visual effects to keep the shell snappy."

                            ToggleRow {
                                label: "Blur Transition"
                                description: "Animated blur when opening panels"
                                checked: Config.performance.blurTransition
                                onToggled: checked => {
                                    Config.performance.blurTransition = checked;
                                }
                            }

                            ToggleRow {
                                label: "Window Preview"
                                description: "Show window thumbnails in overview"
                                checked: Config.performance.windowPreview
                                onToggled: checked => {
                                    Config.performance.windowPreview = checked;
                                }
                            }

                            ToggleRow {
                                label: "Wavy Line"
                                description: "Animated wavy line effect"
                                checked: Config.performance.wavyLine
                                onToggled: checked => {
                                    Config.performance.wavyLine = checked;
                                }
                            }

                            ToggleRow {
                                label: "Disable Cover Art Rotation"
                                description: "Stop the vinyl disc from spinning"
                                checked: !Config.performance.rotateCoverArt
                                onToggled: checked => {
                                    Config.performance.rotateCoverArt = !checked;
                                }
                            }

                            ToggleRow {
                                label: "Optimize Video Wallpapers"
                                description: "Downscale video wallpapers to the screen resolution. First play of each video does a one-time transcode."
                                checked: Config.performance.optimizeVideoWallpapers
                                onToggled: checked => {
                                    Config.performance.optimizeVideoWallpapers = checked;
                                }
                            }

                            ToggleRow {
                                label: "Keep Tabs Loaded"
                                description: "Keep recently opened dashboard tabs resident for snappier switching"
                                checked: Config.performance.dashboardPersistTabs
                                onToggled: checked => {
                                    Config.performance.dashboardPersistTabs = checked;
                                }
                            }

                            SettingsRow {
                                label: "Max Kept Tabs"
                                description: "How many dashboard tabs stay resident"
                                enabled: Config.performance.dashboardPersistTabs

                                SettingsSpinBox {
                                    from: 1
                                    to: 12
                                    value: Config.performance.dashboardMaxPersistentTabs
                                    onValueEdited: newValue => {
                                        Config.performance.dashboardMaxPersistentTabs = newValue;
                                    }
                                }
                            }
                        }
                    }

                    // =====================
                    // SYSTEM SECTION
                    // =====================
                    ColumnLayout {
                        visible: root.currentSection === "system"
                        property string settingsSection: "system"
                        Layout.fillWidth: true
                        spacing: 8

                        Text {
                            text: "System Resources"
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-1)
                            font.weight: Font.Medium
                            color: Colors.overSurfaceVariant
                            Layout.bottomMargin: -4
                        }

                        Text {
                            text: "Configure which disks to monitor"
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-2)
                            color: Colors.overSurfaceVariant
                            opacity: 0.7
                        }

                        // Disks list
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            Repeater {
                                id: disksRepeater
                                model: Config.system.disks

                                delegate: RowLayout {
                                    id: diskRow
                                    required property string modelData
                                    required property int index

                                    Layout.fillWidth: true
                                    spacing: 8

                                    StyledRect {
                                        variant: "common"
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 36
                                        radius: Styling.radius(-2)

                                        TextInput {
                                            id: diskInput
                                            anchors.fill: parent
                                            anchors.margins: 8
                                            font.family: Config.theme.monoFont
                                            font.pixelSize: Styling.monoFontSize(0)
                                            color: Colors.overBackground
                                            selectByMouse: true
                                            clip: true
                                            verticalAlignment: TextInput.AlignVCenter
                                            text: diskRow.modelData

                                            onEditingFinished: {
                                                if (text.trim() !== diskRow.modelData) {
                                                    let newDisks = Config.system.disks.slice();
                                                    newDisks[diskRow.index] = text.trim();
                                                    Config.system.disks = newDisks;
                                                }
                                            }

                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                visible: !diskInput.text && !diskInput.activeFocus
                                                text: "e.g. /, /home..."
                                                font: diskInput.font
                                                color: Colors.overSurfaceVariant
                                            }
                                        }
                                    }

                                    // Remove button
                                    StyledRect {
                                        id: removeDiskButton
                                        variant: removeDiskArea.containsMouse ? "focus" : "common"
                                        Layout.preferredWidth: 36
                                        Layout.preferredHeight: 36
                                        radius: Styling.radius(-2)
                                        visible: disksRepeater.count > 1

                                        Text {
                                            anchors.centerIn: parent
                                            text: Icons.trash
                                            font.family: Icons.font
                                            font.pixelSize: Styling.fontSize(0)
                                            color: Colors.error
                                        }

                                        MouseArea {
                                            id: removeDiskArea
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                let newDisks = Config.system.disks.slice();
                                                newDisks.splice(diskRow.index, 1);
                                                Config.system.disks = newDisks;
                                            }
                                        }

                                        StyledToolTip {
                                            visible: removeDiskArea.containsMouse
                                            tooltipText: "Remove disk"
                                        }
                                    }
                                }
                            }

                            // Add disk button
                            StyledRect {
                                id: addDiskButton
                                variant: addDiskArea.containsMouse ? "primaryfocus" : "primary"
                                Layout.preferredWidth: addDiskContent.width + 24
                                Layout.preferredHeight: 36
                                radius: Styling.radius(-2)

                                Row {
                                    id: addDiskContent
                                    anchors.centerIn: parent
                                    spacing: 6

                                    Text {
                                        text: Icons.plus
                                        font.family: Icons.font
                                        font.pixelSize: Styling.fontSize(0)
                                        color: addDiskButton.item
                                        anchors.verticalCenter: parent.verticalCenter
                                    }

                                    Text {
                                        text: "Add Disk"
                                        font.family: Config.theme.font
                                        font.pixelSize: Styling.fontSize(0)
                                        color: addDiskButton.item
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }

                                MouseArea {
                                    id: addDiskArea
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        let newDisks = Config.system.disks.slice();
                                        newDisks.push("/");
                                        Config.system.disks = newDisks;
                                    }
                                }
                            }
                        }
                    }

                    // =====================
                    // AUTHENTICATION SECTION
                    // =====================
                    ColumnLayout {
                        visible: root.currentSection === "authentication"
                        property string settingsSection: "authentication"
                        Layout.fillWidth: true
                        spacing: 8

                        Text {
                            text: "Authentication"
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-1)
                            font.weight: Font.Medium
                            color: Colors.overSurfaceVariant
                            Layout.bottomMargin: -4
                        }

                        Text {
                            text: "Manage password and fingerprint authentication for the lock screen"
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-2)
                            color: Colors.overSurfaceVariant
                            opacity: 0.7
                        }

                        // ===== Password Settings =====
                        Text {
                            text: "Password"
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(0)
                            font.weight: Font.Medium
                            color: Colors.overBackground
                            Layout.topMargin: 8
                        }

                        Text {
                            text: "Password authentication is always available as a lock-screen fallback."
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-2)
                            color: Colors.overSurfaceVariant
                            opacity: 0.7
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }

                        StyledRect {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 36
                            variant: "common"
                            radius: Styling.radius(-2)

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 8

                                Text {
                                    text: Icons.keyboard
                                    font.family: Icons.font
                                    font.pixelSize: Styling.fontSize(4)
                                    color: Colors.primary
                                }

                                Text {
                                    text: "Change Password"
                                    font.family: Config.theme.font
                                    font.pixelSize: Styling.fontSize(0)
                                    color: Colors.overBackground
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    var proc = Qt.createQmlObject('import Quickshell.Io; Process {}', root);
                                    proc.command = ["passwd"];
                                    proc.onExited.connect(() => proc.destroy());
                                    proc.running = true;
                                }
                            }
                        }

                        SettingsGroup {
                            title: "Fingerprint"
                            description: FingerprintService.available
                                ? (FingerprintService.enrolled
                                    ? "Reader detected · " + FingerprintService.enrolledFingers.length + " fingers enrolled"
                                    : "Reader detected · no fingers enrolled yet")
                                : "No fingerprint reader available"

                            ToggleRow {
                                label: "Enable Fingerprint Auth"
                                description: "Unlock the lock screen with a fingerprint"
                                checked: Config.lockscreen.enableFingerprint
                                enabled: FingerprintService.available
                                onToggled: checked => {
                                    Config.lockscreen.enableFingerprint = checked;
                                }
                            }

                            ToggleRow {
                                label: "Auto-start Scanning"
                                description: "Start scanning as soon as the lock screen appears"
                                checked: Config.lockscreen.fingerprintAutoStart
                                enabled: Config.lockscreen.enableFingerprint && FingerprintService.available
                                onToggled: checked => {
                                    Config.lockscreen.fingerprintAutoStart = checked;
                                }
                            }

                            NumberInputRow {
                                label: "Scan Timeout"
                                description: "Give up and wait for another attempt"
                                value: Config.lockscreen.fingerprintTimeout
                                minValue: 5
                                maxValue: 120
                                suffix: "s"
                                enabled: Config.lockscreen.enableFingerprint && FingerprintService.available
                                onValueEdited: val => {
                                    Config.lockscreen.fingerprintTimeout = val;
                                }
                            }

                            ToggleRow {
                                label: "Fallback to Password"
                                description: "Offer password entry when fingerprint fails"
                                checked: Config.lockscreen.fingerprintFallbackToPassword
                                enabled: Config.lockscreen.enableFingerprint && FingerprintService.available
                                onToggled: checked => {
                                    Config.lockscreen.fingerprintFallbackToPassword = checked;
                                }
                            }
                        }

                        SettingsGroup {
                            title: "Dashboard Authentication"
                            description: "Gate the dashboard behind the same unlock methods."

                            ToggleRow {
                                label: "Require Auth for Dashboard"
                                description: "Ask for fingerprint or password before opening"
                                checked: Config.lockscreen.requireAuthForDashboard
                                onToggled: checked => {
                                    Config.lockscreen.requireAuthForDashboard = checked;
                                }
                            }

                            SettingsRow {
                                label: "Auth Method"
                                description: "How to unlock the dashboard"
                                stacked: true
                                enabled: Config.lockscreen.requireAuthForDashboard

                                SegmentedSwitch {
                                    currentValue: Config.lockscreen.authMethod
                                    model: [
                                        { value: "both", label: "Both" },
                                        { value: "fingerprint", label: "Fingerprint" },
                                        { value: "password", label: "Password" }
                                    ]
                                    onActivated: value => {
                                        Config.lockscreen.authMethod = value;
                                    }
                                }
                            }
                        }

                        // Enrolled fingers list
                        Text {
                            text: "Enrolled Fingers"
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(0)
                            font.weight: Font.Medium
                            color: Colors.overBackground
                            Layout.topMargin: 8
                            visible: FingerprintService.available
                        }

                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            visible: FingerprintService.available
                        }

                        Repeater {
                            model: FingerprintService.enrolledFingers
                            visible: FingerprintService.available

                            delegate: RowLayout {
                                required property string modelData
                                required property int index

                                Layout.fillWidth: true
                                spacing: 8

                                Text {
                                    text: modelData
                                    font.family: Config.theme.font
                                    font.pixelSize: Styling.fontSize(0)
                                    color: Colors.overBackground
                                }

                                Item {
                                    Layout.fillWidth: true
                                }

                                StyledRect {
                                    id: deleteFingerBtn
                                    variant: "error"
                                    Layout.preferredWidth: 32
                                    Layout.preferredHeight: 32
                                    radius: Styling.radius(-2)

                                    Text {
                                        anchors.centerIn: parent
                                        text: Icons.trash
                                        font.family: Icons.font
                                        font.pixelSize: Styling.fontSize(0)
                                        color: deleteFingerBtn.item
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            FingerprintService.deleteFinger(modelData);
                                            FingerprintService.listFingers();
                                        }
                                    }
                                }
                            }
                        }

                        // Enroll new finger button
                        StyledRect {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 36
                            variant: "common"
                            radius: Styling.radius(-2)
                            visible: FingerprintService.available
                            enabled: FingerprintService.available

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 8

                                Text {
                                    text: Icons.plus
                                    font.family: Icons.font
                                    font.pixelSize: Styling.fontSize(2)
                                    color: parent.enabled ? Colors.primary : Colors.overSurfaceVariant
                                }

                                Text {
                                    text: "Enroll New Finger"
                                    font.family: Config.theme.font
                                    font.pixelSize: Styling.fontSize(0)
                                    color: parent.enabled ? Colors.overBackground : Colors.overSurfaceVariant
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                enabled: FingerprintService.available
                                onClicked: {
                                    enrollWizard.open("right-index-finger");
                                }
                            }
                        }

                        // Refresh button
                        StyledRect {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 36
                            variant: "common"
                            radius: Styling.radius(-2)

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 8

                                Text {
                                    text: Icons.arrowCounterClockwise
                                    font.family: Icons.font
                                    font.pixelSize: Styling.fontSize(2)
                                    color: Colors.primary
                                }

                                Text {
                                    text: "Refresh Fingerprint Status"
                                    font.family: Config.theme.font
                                    font.pixelSize: Styling.fontSize(0)
                                    color: Colors.overBackground
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    FingerprintService.update();
                                }
                            }
                        }

                        // Bottom spacing
                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 16
                        }
                    }

                    // =====================
                    // IDLE SECTION
                    // =====================
                    ColumnLayout {
                        visible: root.currentSection === "idle"
                        property string settingsSection: "idle"
                        Layout.fillWidth: true
                        spacing: 8

                        Text {
                            text: "Idle"
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-1)
                            font.weight: Font.Medium
                            color: Colors.overSurfaceVariant
                            Layout.bottomMargin: -4
                        }

                        TextInputRow {
                            label: "Lock Cmd"
                            value: Config.system.idle.general.lock_cmd ?? ""
                            placeholder: "Command to lock screen"
                            onValueEdited: newValue => {
                                if (newValue !== Config.system.idle.general.lock_cmd) {
                                    GlobalStates.markShellChanged();
                                    Config.system.idle.general.lock_cmd = newValue;
                                }
                            }
                        }

                        TextInputRow {
                            label: "Before Sleep"
                            value: Config.system.idle.general.before_sleep_cmd ?? ""
                            placeholder: "Command before sleep"
                            onValueEdited: newValue => {
                                if (newValue !== Config.system.idle.general.before_sleep_cmd) {
                                    GlobalStates.markShellChanged();
                                    Config.system.idle.general.before_sleep_cmd = newValue;
                                }
                            }
                        }

                        TextInputRow {
                            label: "After Sleep"
                            value: Config.system.idle.general.after_sleep_cmd ?? ""
                            placeholder: "Command after sleep"
                            onValueEdited: newValue => {
                                if (newValue !== Config.system.idle.general.after_sleep_cmd) {
                                    GlobalStates.markShellChanged();
                                    Config.system.idle.general.after_sleep_cmd = newValue;
                                }
                            }
                        }

                        Text {
                            text: "Listeners"
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(0)
                            color: Colors.overBackground
                            Layout.topMargin: 8
                        }

                        Repeater {
                            model: Config.system.idle.listeners

                            delegate: ColumnLayout {
                                required property var modelData
                                required property int index

                                Layout.fillWidth: true
                                spacing: 4
                                Layout.bottomMargin: 8

                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 1
                                    color: Colors.surfaceBright
                                    visible: index > 0
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Text {
                                        text: "Listener " + (index + 1)
                                        font.family: Config.theme.font
                                        font.pixelSize: Styling.fontSize(-1)
                                        font.bold: true
                                        color: Styling.srItem("overprimary")
                                    }
                                    Item {
                                        Layout.fillWidth: true
                                    }

                                    StyledRect {
                                        id: deleteListenerBtn
                                        variant: "error"
                                        Layout.preferredWidth: 24
                                        Layout.preferredHeight: 24
                                        radius: Styling.radius(-2)

                                        Text {
                                            anchors.centerIn: parent
                                            text: Icons.trash
                                            font.family: Icons.font
                                            color: deleteListenerBtn.item
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                // Create a copy of the list to ensure change detection
                                                var list = [];
                                                for (var i = 0; i < Config.system.idle.listeners.length; i++)
                                                    list.push(Config.system.idle.listeners[i]);
                                                list.splice(index, 1);
                                                Config.system.idle.listeners = list;
                                                GlobalStates.markShellChanged();
                                            }
                                        }
                                    }
                                }

                                NumberInputRow {
                                    label: "Timeout (s)"
                                    value: modelData.timeout || 0
                                    minValue: 1
                                    maxValue: 7200
                                    onValueEdited: val => {
                                        var list = [];
                                        for (var i = 0; i < Config.system.idle.listeners.length; i++)
                                            list.push(Config.system.idle.listeners[i]);
                                        list[index].timeout = val;
                                        Config.system.idle.listeners = list;
                                        GlobalStates.markShellChanged();
                                    }
                                }

                                TextInputRow {
                                    label: "On Timeout"
                                    value: modelData.onTimeout || ""
                                    onValueEdited: val => {
                                        var list = [];
                                        for (var i = 0; i < Config.system.idle.listeners.length; i++)
                                            list.push(Config.system.idle.listeners[i]);
                                        list[index].onTimeout = val;
                                        Config.system.idle.listeners = list;
                                        GlobalStates.markShellChanged();
                                    }
                                }

                                TextInputRow {
                                    label: "On Resume"
                                    value: modelData.onResume || ""
                                    onValueEdited: val => {
                                        var list = [];
                                        for (var i = 0; i < Config.system.idle.listeners.length; i++)
                                            list.push(Config.system.idle.listeners[i]);
                                        list[index].onResume = val;
                                        Config.system.idle.listeners = list;
                                        GlobalStates.markShellChanged();
                                    }
                                }
                            }
                        }

                        StyledRect {
                            id: addListenerBtn
                            variant: "common"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 32
                            radius: Styling.radius(-2)

                            Text {
                                anchors.centerIn: parent
                                text: "Add Listener"
                                font.family: Config.theme.font
                                font.pixelSize: Styling.fontSize(0)
                                font.bold: true
                                color: addListenerBtn.item
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    var list = [];
                                    if (Config.system.idle.listeners) {
                                        for (var i = 0; i < Config.system.idle.listeners.length; i++)
                                            list.push(Config.system.idle.listeners[i]);
                                    }
                                    list.push({
                                        "timeout": 60,
                                        "onTimeout": "",
                                        "onResume": ""
                                    });
                                    Config.system.idle.listeners = list;
                                    GlobalStates.markShellChanged();
                                }
                            }
                        }
                    }

                    // =====================
                    // TERMINAL SECTION
                    // =====================
                    ColumnLayout {
                        visible: root.currentSection === "terminal"
                        property string settingsSection: "terminal"
                        Layout.fillWidth: true
                        spacing: 8

                        Text {
                            text: "Terminal"
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-1)
                            font.weight: Font.Medium
                            color: Colors.overSurfaceVariant
                            Layout.bottomMargin: -4
                        }

                        Text {
                            text: "Used to open tmux sessions from the dashboard."
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-2)
                            color: Colors.overSurfaceVariant
                            opacity: 0.7
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        TextInputRow {
                            label: "Terminal"
                            value: Config.system.terminal ?? "kitty"
                            placeholder: "foot, kitty, ghostty, alacritty, wezterm…"
                            onValueEdited: newValue => {
                                const v = newValue.trim();
                                if (v !== Config.system.terminal) {
                                    Config.system.terminal = v;
                                }
                            }
                        }

                        ToggleRow {
                            Layout.fillWidth: true
                            label: "Advanced options"
                            description: "Use a custom command template for terminals that do not accept -e"
                            checked: Config.system.terminalAdvanced ?? false
                            onToggled: checked => {
                                if (checked !== Config.system.terminalAdvanced) {
                                    Config.system.terminalAdvanced = checked;
                                }
                            }
                        }

                        ColumnLayout {
                            visible: Config.system.terminalAdvanced ?? false
                            Layout.fillWidth: true
                            spacing: 8

                            Text {
                                text: "$TERMINAL is the binary above. $COMMAND is the full bash command to run."
                                font.family: Config.theme.font
                                font.pixelSize: Styling.fontSize(-2)
                                color: Colors.overSurfaceVariant
                                opacity: 0.7
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }

                            TextInputRow {
                                label: "Open with"
                                value: Config.system.terminalCommand ?? "$TERMINAL -e $COMMAND"
                                placeholder: "$TERMINAL -e $COMMAND"
                                onValueEdited: newValue => {
                                    if (newValue !== Config.system.terminalCommand) {
                                        Config.system.terminalCommand = newValue;
                                    }
                                }
                            }
                        }
                    }

                    // Bottom spacing
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 16
                    }
                }
            }
        }
    }

    // =====================
    // HELPER COMPONENTS
    // =====================

    component NumberInputRow: SettingsRow {
        id: numberInputRowRoot
        property int value: 0
        property int minValue: 0
        property int maxValue: 100
        property string suffix: ""
        signal valueEdited(int newValue)

        SettingsSpinBox {
            value: numberInputRowRoot.value
            from: numberInputRowRoot.minValue
            to: numberInputRowRoot.maxValue
            suffix: numberInputRowRoot.suffix
            enabled: numberInputRowRoot.enabled
            onValueEdited: newValue => numberInputRowRoot.valueEdited(newValue)
        }
    }

    // Inline component for text input rows
    component TextInputRow: RowLayout {
        id: textInputRowRoot
        property string label: ""
        property string value: ""
        property string placeholder: ""
        signal valueEdited(string newValue)

        Layout.fillWidth: true
        spacing: 8

        Text {
            text: textInputRowRoot.label
            font.family: Config.theme.font
            font.pixelSize: Styling.fontSize(0)
            color: Colors.overBackground
            Layout.preferredWidth: 100
        }

        StyledRect {
            variant: "common"
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            radius: Styling.radius(-2)

            TextInput {
                id: textInputField
                anchors.fill: parent
                anchors.margins: 8
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(0)
                color: Colors.overBackground
                selectByMouse: true
                clip: true
                verticalAlignment: TextInput.AlignVCenter

                // Sync text when external value changes
                readonly property string configValue: textInputRowRoot.value
                onConfigValueChanged: {
                    if (!activeFocus && text !== configValue) {
                        text = configValue;
                    }
                }
                Component.onCompleted: text = configValue

                Text {
                    anchors.fill: parent
                    verticalAlignment: Text.AlignVCenter
                    text: textInputRowRoot.placeholder
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(0)
                    color: Colors.overSurfaceVariant
                    visible: textInputField.text === ""
                }

                onEditingFinished: {
                    textInputRowRoot.valueEdited(text);
                }
            }
        }
    }

    // PrefixRow component for prefix inputs
    component PrefixRow: RowLayout {
        id: prefixRow
        property string label: ""
        property string prefixValue: ""
        signal prefixEdited(string newValue)

        spacing: 8

        Text {
            text: prefixRow.label
            font.family: Config.theme.font
            font.pixelSize: Styling.fontSize(0)
            color: Colors.overBackground
            Layout.preferredWidth: 100
        }

        StyledRect {
            variant: "common"
            Layout.preferredWidth: 80
            Layout.preferredHeight: 36
            radius: Styling.radius(-2)

            TextInput {
                id: prefixInput
                anchors.fill: parent
                anchors.margins: 8
                font.family: Config.theme.monoFont
                font.pixelSize: Styling.monoFontSize(0)
                color: Colors.overBackground
                selectByMouse: true
                clip: true
                verticalAlignment: TextInput.AlignVCenter
                horizontalAlignment: TextInput.AlignHCenter
                text: prefixRow.prefixValue
                maximumLength: 4

                onEditingFinished: {
                    if (text !== prefixRow.prefixValue && text.trim() !== "") {
                        prefixRow.prefixEdited(text.trim());
                    }
                }
            }
        }

        Item {
            Layout.fillWidth: true
        }
    }

    component ToggleRow: SettingsRow {
        id: toggleRow
        property bool checked: false
        signal toggled(bool checked)

        SettingsSwitch {
            checked: toggleRow.checked
            enabled: toggleRow.enabled
            onToggled: value => toggleRow.toggled(value)
        }
    }
}
