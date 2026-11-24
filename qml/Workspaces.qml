import Quickshell
import QtQuick
import QtQuick.Layouts
import Niri

RowLayout {
  id: root
  Layout.fillWidth: false
  spacing: 4 * Config.paddingScale

  // niri workspaces are per-output and indexed; draw only this bar's output
  readonly property var win: QsWindow.window
  readonly property string outputName: win && win.screen ? win.screen.name : ""

  Niri {
    id: niri
    Component.onCompleted: connect()
    onErrorOccurred: function(error) {
      console.warn("chillpill-shell: niri IPC error:", error)
    }
  }

  Repeater {
    model: niri.workspaces

    delegate: Rectangle {
      id: wsButton

      // roles exposed by the qml-niri WorkspaceModel
      readonly property bool isActive: model.isActive
      visible: root.outputName === "" || model.output === root.outputName

      Layout.preferredWidth: 17.5 * Config.pillScale
      Layout.preferredHeight: Layout.preferredWidth
      radius: 8 * Config.pillScale
      color: isActive ? Theme.wsActiveBg : Theme.wsInactiveBg

      // animate color transition on workspace switch
      Behavior on color { ColorAnimation { duration: 120 } }

      Text {
        anchors.centerIn: parent
        text: model.name || model.index
        color: wsButton.isActive ? Theme.white : Theme.wsInactiveFg
        font {
          family: Theme.fontFamily
          pixelSize: 9 * Config.pillScale
          weight: 400
        }
      }

      // clickable text buttons
      MouseArea {
        anchors.fill: parent
        onClicked: niri.focusWorkspaceById(model.id)
        cursorShape: Qt.PointingHandCursor
      }
    }
  }
}
