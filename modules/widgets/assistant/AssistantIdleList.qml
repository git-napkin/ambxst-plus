import QtQuick
import QtQuick.Layouts
import qs.modules.theme
import qs.modules.components
import qs.config

StyledRect {
    id: root
    variant: "popup"
    radius: Styling.popupRadius()

    property string filterText: ""
    property int selectedIndex: -1
    signal activated(var item)

    readonly property bool slashMode: (filterText || "").trim().startsWith("/")
    readonly property var items: {
        const raw = (filterText || "").trim();
        const q = raw.toLowerCase();
        const out = [];

        if (root.slashMode) {
            const slashes = [
                { kind: "slash", id: "/new", title: "/new", subtitle: qsTr("Start a fresh chat") },
                { kind: "slash", id: "/model", title: "/model", subtitle: qsTr("Switch model") },
                { kind: "slash", id: "/help", title: "/help", subtitle: qsTr("Show commands") }
            ];
            const needle = q === "/" ? "" : q;
            for (let i = 0; i < slashes.length; i++) {
                if (!needle || slashes[i].title.indexOf(needle) === 0 || slashes[i].title.indexOf(needle) !== -1)
                    out.push(slashes[i]);
            }
            return out;
        }

        const cmds = Config.ai.commands || [];
        for (let i = 0; i < cmds.length; i++) {
            const c = cmds[i] || {};
            const title = c.name || c.id || qsTr("Command");
            if (!q || title.toLowerCase().indexOf(q) !== -1 || String(c.prompt || "").toLowerCase().indexOf(q) !== -1) {
                out.push({
                    kind: "command",
                    id: c.id || title,
                    title: title,
                    subtitle: qsTr("Saved command"),
                    prompt: c.prompt || "",
                    icon: c.icon || Icons.notepad
                });
            }
        }
        return out;
    }

    implicitHeight: items.length > 0 ? Math.min((items.length * 42) + 16, 320) : 0
    visible: items.length > 0

    layer.enabled: true
    layer.effect: Shadow {}

    onFilterTextChanged: selectedIndex = root.slashMode && items.length > 0 ? 0 : -1
    onSlashModeChanged: selectedIndex = root.slashMode && items.length > 0 ? 0 : -1

    function moveSelection(delta) {
        if (items.length === 0)
            return false;
        const next = selectedIndex < 0 ? (delta > 0 ? 0 : items.length - 1) : selectedIndex + delta;
        selectedIndex = Math.max(-1, Math.min(items.length - 1, next));
        if (selectedIndex >= 0)
            list.positionViewAtIndex(selectedIndex, ListView.Contain);
        return selectedIndex >= 0;
    }

    function activateSelected() {
        if (selectedIndex < 0 || selectedIndex >= items.length)
            return false;
        root.activated(items[selectedIndex]);
        return true;
    }

    ListView {
        id: list
        anchors.fill: parent
        anchors.margins: 8
        clip: true
        spacing: 2
        model: root.items
        boundsBehavior: Flickable.StopAtBounds

        delegate: Item {
            id: row
            required property var modelData
            required property int index
            width: list.width
            height: 40

            readonly property bool highlighted: rowArea.containsMouse || root.selectedIndex === row.index

            Rectangle {
                anchors.fill: parent
                radius: Styling.popupRadius() - 8
                color: row.highlighted ? Styling.tint(Colors.overSurface, Styling.hoverAlpha) : "transparent"
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 10

                Text {
                    text: row.modelData.kind === "slash" ? "/" : (row.modelData.icon || Icons.note)
                    font.family: row.modelData.kind === "slash" ? Config.theme.monoFont : Icons.font
                    font.pixelSize: Styling.fontSize(row.modelData.kind === "slash" ? 2 : 2)
                    color: row.highlighted ? Colors.overSurface : Colors.outline
                    Layout.preferredWidth: 16
                    horizontalAlignment: Text.AlignHCenter
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Text {
                        text: row.modelData.title
                        font.family: row.modelData.kind === "slash" ? Config.theme.monoFont : Config.theme.font
                        font.pixelSize: Styling.fontSize(-1)
                        color: Colors.overSurface
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Text {
                        text: row.modelData.subtitle || ""
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-4)
                        color: Colors.outline
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }
            }

            MouseArea {
                id: rowArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.activated(row.modelData)
                onContainsMouseChanged: {
                    if (containsMouse)
                        root.selectedIndex = row.index;
                }
            }
        }
    }
}
