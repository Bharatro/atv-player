from PySide6.QtGui import QKeySequence

from atv_player.ui.help_dialog import ShortcutHelpDialog, shortcut_entries_for


def test_shortcut_help_dialog_hides_maximize_button(qtbot) -> None:
    dialog = ShortcutHelpDialog(shortcut_entries_for("main_window", QKeySequence("Ctrl+Q")))
    qtbot.addWidget(dialog)

    assert dialog.title_bar().maximize_button.isHidden() is True
