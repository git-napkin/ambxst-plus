pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.config
import qs.modules.theme
import qs.modules.components

StyledRect {
    id: root

    // External bound value (Config.*). Local edits go through `text` and only
    // write back on editingFinished/accepted so the binding is not broken.
    property string value: ""
    property string placeholder: ""
    property bool password: false
    property bool mono: false
    property bool multiline: false
    property int areaHeight: 96
    property int maximumLength: 32767

    // Local buffer shown in the input. Prefer binding `value` from Config and
    // reading `text` in onEditingFinished. Alias also exposes textChanged.
    property alias text: input.text

    signal editingFinished
    signal accepted

    variant: "internalbg"
    implicitHeight: multiline ? areaHeight : 40
    implicitWidth: 200
    Layout.fillWidth: true
    Layout.preferredHeight: implicitHeight
    radius: Styling.radius(-2)
    opacity: enabled ? 1 : 0.4

    readonly property bool fieldFocused: input.activeFocus || area.activeFocus

    function syncFromValue() {
        if (root.fieldFocused)
            return;
        if (input.text !== root.value)
            input.text = root.value;
        if (root.multiline && area.text !== root.value)
            area.text = root.value;
    }

    onValueChanged: syncFromValue()
    Component.onCompleted: {
        input.text = root.value;
        if (root.multiline)
            area.text = root.value;
    }

    Rectangle {
        anchors.fill: parent
        radius: parent.radius
        color: "transparent"
        border.width: root.fieldFocused ? 1 : 0
        border.color: Styling.srItem("overprimary")
        opacity: 0.7
    }

    TextInput {
        id: input
        visible: !root.multiline
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        anchors.topMargin: 8
        anchors.bottomMargin: 8
        font.family: root.mono ? Config.theme.monoFont : Config.theme.font
        font.pixelSize: root.mono ? Styling.monoFontSize(0) : Styling.fontSize(0)
        color: Colors.overBackground
        selectedTextColor: Colors.background
        selectionColor: Styling.srItem("overprimary")
        verticalAlignment: TextInput.AlignVCenter
        clip: true
        selectByMouse: true
        echoMode: root.password ? TextInput.Password : TextInput.Normal
        maximumLength: root.maximumLength
        enabled: root.enabled
        onEditingFinished: root.editingFinished()
        onAccepted: root.accepted()

        Text {
            anchors.fill: parent
            verticalAlignment: Text.AlignVCenter
            text: root.placeholder
            font: input.font
            color: Colors.overSurfaceVariant
            opacity: 0.7
            visible: input.text === "" && !input.activeFocus
            elide: Text.ElideRight
        }
    }

    TextEdit {
        id: area
        visible: root.multiline
        anchors.fill: parent
        anchors.margins: 12
        font.family: root.mono ? Config.theme.monoFont : Config.theme.font
        font.pixelSize: root.mono ? Styling.monoFontSize(-1) : Styling.fontSize(-1)
        color: Colors.overBackground
        selectedTextColor: Colors.background
        selectionColor: Styling.srItem("overprimary")
        wrapMode: TextEdit.Wrap
        clip: true
        selectByMouse: true
        enabled: root.enabled
        onTextChanged: {
            if (activeFocus && text !== input.text)
                input.text = text;
        }
        onActiveFocusChanged: {
            if (!activeFocus)
                root.editingFinished();
        }

        Connections {
            target: input
            function onTextChanged() {
                if (!area.activeFocus && area.text !== input.text)
                    area.text = input.text;
            }
        }

        Text {
            anchors.fill: parent
            text: root.placeholder
            font: area.font
            color: Colors.overSurfaceVariant
            opacity: 0.7
            visible: area.text === "" && !area.activeFocus
            wrapMode: Text.Wrap
        }
    }
}
