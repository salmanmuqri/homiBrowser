import sys
import sqlite3
import os
from datetime import datetime
from PyQt5.QtWidgets import (QHBoxLayout, QMessageBox, QApplication, QMainWindow, QToolBar, QLineEdit, QPushButton, QVBoxLayout, QWidget, QTabWidget, QDialog, QTableWidget, QTableWidgetItem, QMenu, QAction, QComboBox, QLabel, QProgressBar, QCheckBox)
from PyQt5.QtCore import QUrl, Qt, QSettings, QTimer
from PyQt5.QtWebEngineWidgets import (QWebEngineView, QWebEngineProfile, QWebEngineSettings, QWebEnginePage, QWebEngineDownloadItem)
from PyQt5.QtGui import QIcon, QColor, QCursor, QPalette


class CustomWebEngineView(QWebEngineView):
    def __init__(self, parent=None, is_incognito=False):
        super().__init__(parent)
        self.browser = None
        self.current_link = None
        
        if is_incognito:
            self.profile = QWebEngineProfile()
            self.profile.setHttpCacheType(QWebEngineProfile.NoCache)
            self.profile.setPersistentStoragePath("")
            self.page().setProfile(self.profile)
        else:
            self.profile = QWebEngineProfile.defaultProfile()

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.prepare_context_menu)

    def prepare_context_menu(self, pos):
        self.current_link = None
        self.page().runJavaScript("""
            (function() {
                var element = document.elementFromPoint(arguments[0], arguments[1]);
                var link = element ? element.closest('a') : null;
                return link ? link.href : null;
            })(event.clientX, event.clientY);
        """, self.show_context_menu)

    def show_context_menu(self, link):
        self.current_link = link
        context_menu = QMenu(self)

        back_action = context_menu.addAction("Back")
        back_action.triggered.connect(self.back)
    
        forward_action = context_menu.addAction("Forward")
        forward_action.triggered.connect(self.forward)

        if link:
            context_menu.addSeparator()
            
            open_new_tab_action = context_menu.addAction("Open Link in New Tab")
            open_new_tab_action.triggered.connect(lambda: self.open_link_in_new_tab(link))

            copy_link_action = context_menu.addAction("Copy Link Address")
            copy_link_action.triggered.connect(lambda: self.copy_link(link))

        context_menu.exec_(self.mapToGlobal(QCursor.pos()))

    def open_link_in_new_tab(self, link):
        if self.browser and link:
            self.browser.add_new_tab(link)

    def copy_link(self, link):
        if link:
            clipboard = QApplication.clipboard()
            clipboard.setText(link)

    def back(self):
        self.page().triggerAction(QWebEnginePage.Back)

    def forward(self):
        self.page().triggerAction(QWebEnginePage.Forward)

class BookmarkManager(QDialog):
    def __init__(self, connection, parent=None):
        super().__init__(parent)
        self.conn = connection
        self.setWindowTitle("Bookmark Manager")
        self.resize(800, 500)
        
        layout = QVBoxLayout()
        
        input_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter URL")
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Enter Title (Optional)")
        
        add_btn = QPushButton("Add Bookmark")
        add_btn.clicked.connect(self.add_bookmark)
        
        input_layout.addWidget(self.url_input)
        input_layout.addWidget(self.title_input)
        input_layout.addWidget(add_btn)
        
        layout.addLayout(input_layout)
        
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Title", "URL", "Actions"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        
        self.load_bookmarks()
        
        self.setLayout(layout)
        
    def load_bookmarks(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT title, url FROM bookmarks ORDER BY title")
        bookmarks = cursor.fetchall()
        
        self.table.setRowCount(len(bookmarks))
        for row, (title, url) in enumerate(bookmarks):
            title_item = QTableWidgetItem(title or "Untitled")
            self.table.setItem(row, 0, title_item)
            
            url_item = QTableWidgetItem(url)
            self.table.setItem(row, 1, url_item)
            
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            
            delete_btn = QPushButton("Delete")
            delete_btn.clicked.connect(lambda _, u=url: self.delete_bookmark(u))
            
            open_btn = QPushButton("Open")
            open_btn.clicked.connect(lambda _, u=url: self.open_bookmark(u))
            
            actions_layout.addWidget(delete_btn)
            actions_layout.addWidget(open_btn)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            
            self.table.setCellWidget(row, 2, actions_widget)
    
    def add_bookmark(self):
        url = self.url_input.text().strip()
        title = self.title_input.text().strip() or None
    
        if not url:
            QMessageBox.warning(self, "Error", "URL cannot be empty")
            return

        try:
            cursor = self.conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO bookmarks (title, url) VALUES (?, ?)", 
                           (title, url))
            self.conn.commit()

            self.url_input.clear()
            self.title_input.clear()

            self.load_bookmarks()

        except sqlite3.Error as e:
            QMessageBox.critical(self, "Database Error", str(e))
    
    
    def delete_bookmark(self, url):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM bookmarks WHERE url = ?", (url,))
        self.conn.commit()
        self.load_bookmarks()
    
    def open_bookmark(self, url):
        if self.parent():
            self.parent().add_new_tab(url)
        self.close()

class HistoryViewer(QDialog):
    def __init__(self, connection, parent=None):
        super().__init__(parent)
        self.conn = connection
        self.setWindowTitle("Browsing History")
        self.resize(800, 500)
        
        layout = QVBoxLayout()
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Title", "URL", "Visited At", "Actions"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        
        clear_btn = QPushButton("Clear History")
        clear_btn.clicked.connect(self.clear_history)
        layout.addWidget(clear_btn)
        
        self.load_history()
        
        self.setLayout(layout)
    
    def load_history(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT title, url, visited_at 
            FROM history 
            ORDER BY visited_at DESC
        """)
        history = cursor.fetchall()
        
        self.table.setRowCount(len(history))
        for row, (title, url, visited_at) in enumerate(history):
            title_item = QTableWidgetItem(title or "Untitled")
            self.table.setItem(row, 0, title_item)
            
            url_item = QTableWidgetItem(url)
            self.table.setItem(row, 1, url_item)
            
            visited_item = QTableWidgetItem(str(visited_at))
            self.table.setItem(row, 2, visited_item)
            
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            
            open_btn = QPushButton("Open")
            open_btn.clicked.connect(lambda _, u=url: self.open_history_item(u))
            
            actions_layout.addWidget(open_btn)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            
            self.table.setCellWidget(row, 3, actions_widget)
    
    def open_history_item(self, url):
        if self.parent():
            self.parent().add_new_tab(url)
        self.close()
    
    def clear_history(self):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM history")
        self.conn.commit()
        self.load_history()

class CustomWebPage(QWebEnginePage):
    def createWindow(self, _type):
        return self.view().browser.create_new_tab()

class DownloadItem(QWidget):
    def __init__(self, download):
        super().__init__()
        layout = QVBoxLayout(self)
        
        self.download = download
        
        filename_label = QLabel(download.suggestedFileName())
        layout.addWidget(filename_label)
        
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        download.downloadProgress.connect(self.update_progress)
        download.finished.connect(self.download_finished)
        
    def update_progress(self, received, total):
        if total > 0:
            self.progress_bar.setValue(int((received / total) * 100))
    
    def download_finished(self):
        self.progress_bar.setValue(100)

class DownloadManager(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Download Manager")
        self.resize(500, 300)
        
        layout = QVBoxLayout(self)
        self.downloads_layout = QVBoxLayout()
        layout.addLayout(self.downloads_layout)
    
    def add_download(self, download):
        download_item = DownloadItem(download)
        self.downloads_layout.addWidget(download_item)
        self.show()

class WebBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HomiBrowser")
        self.resize(1200, 800)
        
        self.init_database()
        
        main_layout = QVBoxLayout()
        
        nav_toolbar = QToolBar()
        self.addToolBar(nav_toolbar)
        
        self.back_btn = QPushButton("←")
        self.back_btn.clicked.connect(self.navigate_back)
        nav_toolbar.addWidget(self.back_btn)
        
        self.forward_btn = QPushButton("→")
        self.forward_btn.clicked.connect(self.navigate_forward)
        nav_toolbar.addWidget(self.forward_btn)
        
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.clicked.connect(self.refresh_page)
        nav_toolbar.addWidget(self.refresh_btn)
        
        new_tab_btn = QPushButton("+")
        new_tab_btn.clicked.connect(self.add_new_tab)
        nav_toolbar.addWidget(new_tab_btn)
        
        self.search_engine_combo = QComboBox()
        search_engines = ["Google", "Bing", "DuckDuckGo"]
        self.search_engine_combo.addItems(search_engines)
        nav_toolbar.addWidget(QLabel("Search:"))
        nav_toolbar.addWidget(self.search_engine_combo)
        
        self.url_bar = QLineEdit()
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        nav_toolbar.addWidget(self.url_bar)
        
        self.bookmark_btn = QPushButton("☆")
        self.bookmark_btn.clicked.connect(self.toggle_bookmark)
        nav_toolbar.addWidget(self.bookmark_btn)
        
        bookmarks_manager_btn = QPushButton("Bookmarks")
        bookmarks_manager_btn.clicked.connect(self.view_bookmark_manager)
        nav_toolbar.addWidget(bookmarks_manager_btn)
        
        history_btn = QPushButton("History")
        history_btn.clicked.connect(self.view_history)
        nav_toolbar.addWidget(history_btn)
        
        self.incognito_checkbox = QCheckBox("Incognito")
        self.incognito_checkbox.stateChanged.connect(self.on_incognito_state_changed)
        nav_toolbar.addWidget(self.incognito_checkbox)
        
        download_btn = QPushButton("Downloads")
        download_btn.clicked.connect(self.show_download_manager)
        nav_toolbar.addWidget(download_btn)
        
        reopen_tab_btn = QPushButton("↩ Reopen Tab")
        reopen_tab_btn.clicked.connect(self.reopen_last_tab)
        nav_toolbar.addWidget(reopen_tab_btn)
        
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        
        main_layout.addWidget(self.tabs)
        
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        
        self.download_manager = DownloadManager(self)
        
        self.closed_tabs = []
        
        self.add_new_tab()
    
    def on_incognito_state_changed(self, state):
        current_tab = self.tabs.currentWidget()
        if state == Qt.Checked:
            current_tab.page().setProfile(
                QWebEngineProfile.defaultProfile().createOffTheRecordProfile()
            )
        else:
            current_tab.page().setProfile(QWebEngineProfile.defaultProfile())
    
    def navigate_to_url(self):
        current_web_view = self.tabs.currentWidget()
        url = self.url_bar.text()
        
        if not url.startswith(('http://', 'https://')):
            search_engine = self.search_engine_combo.currentText()
            if search_engine == "Google":
                url = f'https://www.google.com/search?q={url}'
            elif search_engine == "Bing":
                url = f'https://www.bing.com/search?q={url}'
            elif search_engine == "DuckDuckGo":
                url = f'https://duckduckgo.com/?q={url}'
        
        current_web_view.load(QUrl(url))

    def handle_download(self, download):
        download_path = os.path.expanduser("~/Downloads")
        os.makedirs(download_path, exist_ok=True)
        
        download.setDownloadDirectory(download_path)
        download.accept()
        
        self.download_manager.add_download(download)
    
    def show_download_manager(self):
        self.download_manager.show()

    def toggle_dark_mode(self):
        app = QApplication.instance()
        if app.styleSheet() == "":
            app.setStyleSheet("""
                QWidget {
                    background-color: #2b2b2b;
                    color: white;
                }
                QLineEdit, QTableWidget {
                    background-color: #3c3f41;
                    color: white;
                }
            """)
            for i in range(self.tabs.count()):
                web_view = self.tabs.widget(i)
                web_view.settings().setAttribute(
                    QWebEngineSettings.ForceDarkMode, True
                )
        else:
            app.setStyleSheet("")
            for i in range(self.tabs.count()):
                web_view = self.tabs.widget(i)
                web_view.settings().setAttribute(
                    QWebEngineSettings.ForceDarkMode, False
                )

    def toggle_incognito_mode(self):
        current_web_view = self.tabs.currentWidget()
        profile = current_web_view.page().profile()
        if profile.persistentStoragePath():
            incognito_profile = QWebEngineProfile.defaultProfile()
            incognito_profile.setHttpCacheType(QWebEngineProfile.NoCache)
            incognito_profile.setPersistentStoragePath("")
            current_web_view.page().setProfile(incognito_profile)
            self.incognito_btn.setText("🕶️💡")  
        else:
            current_web_view.page().setProfile(QWebEngineProfile.defaultProfile())
            self.incognito_btn.setText("🕶️")

    def reopen_last_tab(self):
        if self.closed_tabs:
            last_tab = self.closed_tabs.pop()
            new_tab = self.add_new_tab(last_tab['url'])
            new_tab.setWindowTitle(last_tab.get('title', 'Reopened Tab'))
    
    def init_database(self):
        self.conn = sqlite3.connect('browser_data.db')
        cursor = self.conn.cursor()
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS bookmarks
                          (id INTEGER PRIMARY KEY, 
                           title TEXT, 
                           url TEXT UNIQUE)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS history
                          (id INTEGER PRIMARY KEY, 
                           title TEXT, 
                           url TEXT, 
                           visited_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        self.conn.commit()
    
    def create_new_tab_button(self):
        new_tab_btn = QPushButton("+")
        new_tab_btn.clicked.connect(self.add_new_tab)
        return new_tab_btn
    
    def add_new_tab(self, url=None):
        is_incognito = self.incognito_checkbox.isChecked()
        
        web_view = CustomWebEngineView(parent=self, is_incognito=is_incognito)
        
        web_view.browser = self
        web_view.urlChanged.connect(self.update_url_bar)
        web_view.titleChanged.connect(self.update_tab_title)
        
        web_view.page().profile().downloadRequested.connect(self.handle_download)
        
        if is_incognito:
            web_view.page().setProfile(
                QWebEngineProfile.defaultProfile().createOffTheRecordProfile()
            )
        
        if url:
            web_view.load(QUrl(url))
        else:
            web_view.load(QUrl("https://www.google.com"))
        
        tab_index = self.tabs.addTab(web_view, "New Tab")
        self.tabs.setCurrentIndex(tab_index)
        
        return web_view
    
    def create_new_tab(self):
        return self.add_new_tab()
    
    def handle_download(self, download):
        download_path = os.path.expanduser("~/Downloads")
        os.makedirs(download_path, exist_ok=True)
        
        filename = download.suggestedFileName()
        download.setDownloadDirectory(download_path)
        download.accept()
    
    def navigate_to_url(self):
        current_web_view = self.tabs.currentWidget()
        url = self.url_bar.text()
        
        if not url.startswith(('http://', 'https://')):
            search_engine = self.search_engine_combo.currentText()
            if search_engine == "Google":
                url = f'https://www.google.com/search?q={url}'
            elif search_engine == "Bing":
                url = f'https://www.bing.com/search?q={url}'
            elif search_engine == "DuckDuckGo":
                url = f'https://duckduckgo.com/?q={url}'
        
        current_web_view.load(QUrl(url))
    
    def update_url_bar(self, url):
        self.url_bar.setText(url.toString())
        self.update_bookmark_button()

        self.add_to_history(self.tabs.currentWidget().title(), url.toString())

    
    def update_tab_title(self, title):
        current_tab_index = self.tabs.currentIndex()
        self.tabs.setTabText(current_tab_index, title[:20] + "...")
    
    def navigate_back(self):
        current_web_view = self.tabs.currentWidget()
        current_web_view.back()
    
    def navigate_forward(self):
        current_web_view = self.tabs.currentWidget()
        current_web_view.forward()
    
    def refresh_page(self):
        current_web_view = self.tabs.currentWidget()
        current_web_view.reload()
    
    def close_tab(self, index):
        web_view = self.tabs.widget(index)
        
        if not web_view.page().profile().isOffTheRecord():
            self.closed_tabs.append({
                'url': web_view.url().toString(),
                'title': web_view.title()
            })
        
        web_view.page().runJavaScript("document.querySelectorAll('video, audio').forEach(media => media.pause());")
        
        self.tabs.removeTab(index)
        
        if self.tabs.count() == 0:
            self.add_new_tab()
    
    def toggle_bookmark(self):
        current_web_view = self.tabs.currentWidget()
        url = current_web_view.url().toString()
        title = current_web_view.title()
        
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT * FROM bookmarks WHERE url = ?", (url,))
        existing_bookmark = cursor.fetchone()
        
        if existing_bookmark:
            cursor.execute("DELETE FROM bookmarks WHERE url = ?", (url,))

            self.bookmark_btn.setText("☆")
        else:
            cursor.execute("INSERT OR REPLACE INTO bookmarks (title, url) VALUES (?, ?)", 
                           (title, url))

            self.bookmark_btn.setText("★")
        
        self.conn.commit()
    
    def update_bookmark_button(self):
        current_web_view = self.tabs.currentWidget()
        url = current_web_view.url().toString()
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM bookmarks WHERE url = ?", (url,))
        existing_bookmark = cursor.fetchone()
        
        self.bookmark_btn.setText("★" if existing_bookmark else "☆")

    def view_bookmark_manager(self):

        bookmark_manager = BookmarkManager(self.conn, self)
        bookmark_manager.exec_()
        
    def add_to_history(self, title, url):
        if not self.incognito_checkbox.isChecked():
            cursor = self.conn.cursor()
            try:
                cursor.execute("INSERT INTO history (title, url) VALUES (?, ?)", 
                           (title, url))
                self.conn.commit()
            except sqlite3.Error as e:
                print(f"Error adding to history: {e}")
    
    def view_history(self):
        history_viewer = HistoryViewer(self.conn, self)
        history_viewer.exec_()

    def back(self):
        current_web_view = self.tabs.currentWidget()
        current_web_view.back()

    def forward(self):
        current_web_view = self.tabs.currentWidget()
        current_web_view.forward()

    def reload(self):
        current_web_view = self.tabs.currentWidget()
        
        current_web_view.reload()
        
    def mousePressEvent(self, event):
        print("Mouse Press Event: ", event.button()) 
        super().mousePressEvent(event)


def main():
    app = QApplication(sys.argv)
    browser = WebBrowser()
    browser.show()
    sys.exit(app.exec_())

if __name__ == "__main__":

    main()
