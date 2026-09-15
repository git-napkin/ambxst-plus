pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qs.modules.theme
import qs.config

// Searchable dropdown of every font family available on the system.
// Empty `value` means "use the shell default icon font" (Icons.font).
Item {
    id: root

    property string value: ""
    // When true, offers an empty "Default" entry (used by launcher icon font).
    property bool allowEmpty: true
    property string emptyLabel: "Default"
    property string emptyFamily: Icons.font
    signal valueSelected(string newValue)

    implicitHeight: 40
    implicitWidth: 200
    Layout.fillWidth: true
    Layout.preferredHeight: implicitHeight

    property string filterText: ""
    property var filteredModel: []

    readonly property var systemFonts: {
        const families = Qt.fontFamilies();
        return families.slice().sort((a, b) => a.localeCompare(b, undefined, {
                sensitivity: "base"
            }));
    }

    readonly property string displayText: root.value !== "" ? root.value : (root.allowEmpty ? root.emptyLabel : "Select font...")
    readonly property string displayFamily: root.value !== "" ? root.value : root.emptyFamily

    function rebuildFilter() {
        const q = root.filterText.trim().toLowerCase();
        const out = [];
        if (root.allowEmpty) {
            const defaultHaystack = (root.emptyLabel + " " + root.emptyFamily).toLowerCase();
            if (q === "" || defaultHaystack.includes(q)) {
                out.push({
                        label: root.emptyLabel,
                        family: "",
                        previewFamily: root.emptyFamily
                    });
            }
        }
        const fonts = root.systemFonts;
        for (let i = 0; i < fonts.length; i++) {
            const name = fonts[i];
            if (q === "" || name.toLowerCase().includes(q)) {
                out.push({
                        label: name,
                        family: name,
                        previewFamily: name
                    });
            }
        }
        // Keep a configured-but-missing font visible so the selection isn't blank.
        if (root.value !== "" && !fonts.includes(root.value) && (q === "" || root.value.toLowerCase().includes(q))) {
            out.splice(root.allowEmpty ? Math.min(1, out.length) : 0, 0, {
                    label: root.value + " (missing)",
                    family: root.value,
                    previewFamily: root.emptyFamily
                });
        }
        root.filteredModel = out;
    }

    function openPopup() {
        root.filterText = "";
        filterField.text = "";
        root.rebuildFilter();

        if (Overlay.overlay) {
            fontPopup.parent = Overlay.overlay;
            const pos = trigger.mapToItem(Overlay.overlay, 0, root.height + 4);
            fontPopup.x = Math.max(0, pos.x);
            fontPopup.y = Math.max(0, pos.y);
        } else {
            fontPopup.parent = root;
            fontPopup.x = 0;
            fontPopup.y = root.height + 4;
        }
        fontPopup.width = Math.max(root.width, 280);
        fontPopup.open();
    }

    function selectFamily(family) {
        if (!root.allowEmpty && family === "")
            return;
        if (family !== root.value)
            root.valueSelected(family);
        fontPopup.close();
    }

    function scrollToCurrent() {
        for (let i = 0; i < root.filteredModel.length; i++) {
            if (root.filteredModel[i].family === root.value) {
                fontList.positionViewAtIndex(i, ListView.Center);
                return;
            }
        }
    }

    Component.onCompleted: rebuildFilter()
    onFilterTextChanged: rebuildFilter()
    onSystemFontsChanged: rebuildFilter()
    onEmptyLabelChanged: rebuildFilter()
    onEmptyFamilyChanged: rebuildFilter()
    onAllowEmptyChanged: rebuildFilter()
    onValueChanged: {
        if (!fontPopup.visible)
            rebuildFilter();
    }

    StyledRect {
        id: trigger
        anchors.fill: parent
        variant: triggerMa.containsMouse || fontPopup.visible ? "focus" : "common"
        radius: Styling.radius(-2)

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            spacing: 8

            Text {
                text: root.displayText
                font.family: root.displayFamily
                font.pixelSize: Styling.fontSize(0)
                color: Colors.overBackground
                elide: Text.ElideRight
                Layout.fillWidth: true
                verticalAlignment: Text.AlignVCenter
            }

            Text {
                text: Icons.caretDown
                font.family: Icons.font
                font.pixelSize: Styling.fontSize(4)
                color: Colors.overBackground
            }
        }

        MouseArea {
            id: triggerMa
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                if (fontPopup.visible)
                    fontPopup.close();
                else
                    root.openPopup();
            }
        }
    }

    Popup {
        id: fontPopup
        parent: root
        width: Math.max(root.width, 280)
        padding: 8
        modal: false
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        onOpened: {
            filterField.forceActiveFocus();
            Qt.callLater(root.scrollToCurrent);
        }

        onClosed: {
            root.filterText = "";
            filterField.text = "";
        }

        background: StyledRect {
            variant: "popup"
            radius: Styling.radius(-2)
        }

        contentItem: ColumnLayout {
            spacing: 8

            StyledRect {
                Layout.fillWidth: true
                Layout.preferredHeight: 32
                variant: "common"
                radius: Styling.radius(-2)

                TextInput {
                    id: filterField
                    anchors.fill: parent
                    anchors.margins: 8
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(0)
                    color: Colors.overBackground
                    selectByMouse: true
                    clip: true
                    verticalAlignment: TextInput.AlignVCenter
                    onTextChanged: root.filterText = text

                    Keys.onReturnPressed: {
                        if (root.filteredModel.length > 0)
                            root.selectFamily(root.filteredModel[0].family);
                    }
                    Keys.onEnterPressed: {
                        if (root.filteredModel.length > 0)
                            root.selectFamily(root.filteredModel[0].family);
                    }
                    Keys.onDownPressed: fontList.forceActiveFocus()
                }

                Text {
                    anchors.fill: parent
                    anchors.margins: 8
                    verticalAlignment: Text.AlignVCenter
                    text: "Search fonts..."
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(0)
                    color: Colors.overSurfaceVariant
                    visible: filterField.text === ""
                }
            }

            ListView {
                id: fontList
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(contentHeight, 280)
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: root.filteredModel
                currentIndex: {
                    for (let i = 0; i < root.filteredModel.length; i++) {
                        if (root.filteredModel[i].family === root.value)
                            return i;
                    }
                    return -1;
                }
                ScrollBar.vertical: ScrollBar {
                    policy: fontList.contentHeight > fontList.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
                }

                delegate: ItemDelegate {
                    id: fontDelegate
                    required property var modelData
                    required property int index

                    width: ListView.view.width
                    height: 36
                    highlighted: fontList.currentIndex === index || hovered

                    background: Rectangle {
                        color: fontDelegate.highlighted ? Colors.surfaceContainerHigh : "transparent"
                        radius: Styling.radius(-2)
                    }

                    contentItem: Text {
                        text: fontDelegate.modelData.label
                        font.family: fontDelegate.modelData.previewFamily
                        font.pixelSize: Styling.fontSize(0)
                        color: Colors.overBackground
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 8
                        rightPadding: 8
                    }

                    onClicked: root.selectFamily(fontDelegate.modelData.family)
                }
            }

            Text {
                visible: root.filteredModel.length === 0
                text: "No fonts match"
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(-1)
                color: Colors.overSurfaceVariant
                Layout.alignment: Qt.AlignHCenter
            }
        }
    }
}
