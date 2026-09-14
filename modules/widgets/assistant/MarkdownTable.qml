import QtQuick
import QtQuick.Layouts
import qs.modules.theme
import qs.modules.components
import qs.config

StyledRect {
    id: root
    property var headers: []
    property var rows: []
    property var aligns: []

    variant: "internalbg"
    radius: Styling.radius(-4)
    implicitHeight: grid.implicitHeight + 20
    clip: true

    readonly property int colCount: Math.max(1, (headers && headers.length) ? headers.length : 1)
    readonly property bool hasHeaders: {
        const h = headers || [];
        for (let i = 0; i < h.length; i++) {
            if (String(h[i] || "").length)
                return true;
        }
        return false;
    }

    readonly property var cells: {
        const out = [];
        const cols = root.colCount;
        const h = headers || [];
        const a = aligns || [];
        if (root.hasHeaders) {
            for (let c = 0; c < cols; c++) {
                out.push({
                    text: String(h[c] || ""),
                    align: a[c] || "left",
                    header: true
                });
            }
        }
        const rs = rows || [];
        for (let r = 0; r < rs.length; r++) {
            const row = rs[r] || [];
            for (let c = 0; c < cols; c++) {
                out.push({
                    text: String(row[c] || ""),
                    align: a[c] || "left",
                    header: false
                });
            }
        }
        return out;
    }

    function _hAlign(name) {
        if (name === "center")
            return Text.AlignHCenter;
        if (name === "right")
            return Text.AlignRight;
        return Text.AlignLeft;
    }

    GridLayout {
        id: grid
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 10
        columns: root.colCount
        columnSpacing: 12
        rowSpacing: 6

        Repeater {
            model: root.cells
            delegate: Text {
                required property var modelData
                required property int index
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                Layout.row: Math.floor(index / root.colCount)
                Layout.column: index % root.colCount
                wrapMode: Text.Wrap
                textFormat: Text.MarkdownText
                text: modelData.text || ""
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(-2)
                font.weight: modelData.header ? Font.DemiBold : Font.Normal
                color: modelData.header ? Colors.outline : Colors.overSurface
                horizontalAlignment: root._hAlign(modelData.align)

                Rectangle {
                    visible: modelData.header
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: -3
                    height: 1
                    color: Colors.outline
                    opacity: 0.25
                }
            }
        }
    }
}
