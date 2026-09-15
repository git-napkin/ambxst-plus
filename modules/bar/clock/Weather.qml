import QtQuick
import QtQuick.Layouts
import qs.config
import qs.modules.theme
import qs.modules.components
import qs.modules.services

StyledRect {
    id: weatherContainer
    variant: "bg"
    visible: weatherVisible

    property string currentDayAbbrev: ""
    property string weatherSymbol: WeatherService.weatherSymbol
    property string weatherTemp: WeatherService.dataAvailable ? (Math.round(WeatherService.currentTemp) + "°" + Config.weather.unit) : ""

    property bool weatherVisible: WeatherService.dataAvailable
    required property var bar
    property string orientation: "horizontal"
    property bool vertical: orientation === "vertical"

    Layout.preferredWidth: vertical ? 36 : rowLayout.implicitWidth + 24
    implicitHeight: vertical ? columnLayout.implicitHeight + 20 : 36
    Layout.preferredHeight: implicitHeight

    RowLayout {
        id: rowLayout
        visible: !vertical
        anchors.centerIn: parent
        spacing: 8

        Text {
            id: symbolDisplay
            text: weatherContainer.weatherSymbol
            color: Colors.overBackground
            font.pixelSize: Styling.fontSize(2)
            font.family: Icons.font
            font.bold: true
            layer.enabled: true
            layer.effect: Shadow {}
        }

        Separator {
            id: separator
            vert: true
        }

        Text {
            id: tempDisplay
            text: weatherContainer.weatherTemp
            color: Colors.overBackground
            font.pixelSize: Config.theme.fontSize
            font.family: Config.theme.font
            font.bold: true
        }
    }

    ColumnLayout {
        id: columnLayout
        visible: vertical
        anchors.centerIn: parent
        spacing: 4
        Layout.alignment: Qt.AlignHCenter

        Text {
            id: symbolDisplayV
            text: weatherContainer.weatherSymbol
            color: Colors.overBackground
            font.pixelSize: Styling.fontSize(2)
            font.family: Icons.font
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.NoWrap
            Layout.alignment: Qt.AlignHCenter
        }

        Separator {
            id: separatorV
            vert: false
            Layout.alignment: Qt.AlignHCenter
        }

        Text {
            id: tempDisplayV
            text: weatherContainer.vertical && weatherContainer.weatherTemp.length > 0 ? weatherContainer.weatherTemp.slice(0, -1) : weatherContainer.weatherTemp
            color: Colors.overBackground
            font.pixelSize: Config.theme.fontSize
            font.family: Config.theme.font
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.NoWrap
            Layout.alignment: Qt.AlignHCenter
        }
    }

    function scheduleNextDayUpdate() {
        var now = new Date();
        var next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 1);
        var ms = next - now;
        dayUpdateTimer.interval = ms;
        dayUpdateTimer.start();
    }

    function updateDay() {
        var now = new Date();
        var day = Qt.formatDateTime(now, Qt.locale(), "ddd");
        weatherContainer.currentDayAbbrev = day.slice(0, 3).charAt(0).toUpperCase() + day.slice(1, 3);
        scheduleNextDayUpdate();
    }

    Timer {
        id: dayUpdateTimer
        repeat: false
        running: false
        onTriggered: updateDay()
    }

    Component.onCompleted: updateDay()
}
