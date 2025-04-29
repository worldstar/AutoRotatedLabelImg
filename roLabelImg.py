#!/usr/bin/env python
# -*- coding: utf8 -*-
import codecs
import os.path
import re
import sys
import subprocess
import shutil
import xml.etree.ElementTree as ET
import ollama

from functools import partial
from collections import defaultdict

try:
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtWidgets import *
    from PyQt5 import QtWidgets
except ImportError:
    # needed for py3+qt4
    # Ref:
    # http://pyqt.sourceforge.net/Docs/PyQt4/incompatible_apis.html
    # http://stackoverflow.com/questions/21217399/pyqt4-qtcore-qvariant-object-instead-of-a-string
    if sys.version_info.major >= 3:
        import sip
        sip.setapi('QVariant', 2)
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *

import resources
# Add internal libs
dir_name = os.path.abspath(os.path.dirname(__file__))
libs_path = os.path.join(dir_name, 'libs')
sys.path.insert(0, libs_path)
from lib import struct, newAction, newIcon, addActions, fmtShortcut
from shape import Shape, DEFAULT_LINE_COLOR, DEFAULT_FILL_COLOR
from canvas import Canvas
from zoomWidget import ZoomWidget
from labelDialog import LabelDialog
from colorDialog import ColorDialog
from labelFile import LabelFile, LabelFileError
from toolBar import ToolBar
from pascal_voc_io import PascalVocReader
from pascal_voc_io import XML_EXT
from ustr import ustr
from make_xml_file import Make_xml

__appname__ = 'roLabelImg'

# Utility functions and classes.


def have_qstring():
    '''p3/qt5 get rid of QString wrapper as py3 has native unicode str type'''
    return not (sys.version_info.major >= 3 or QT_VERSION_STR.startswith('5.'))


def util_qt_strlistclass():
    return QStringList if have_qstring() else list


class WindowMixin(object):

    def menu(self, title, actions=None):
        menu = self.menuBar().addMenu(title)
        if actions:
            addActions(menu, actions)
        return menu

    def toolbar(self, title, actions=None):
        toolbar = ToolBar(title)
        toolbar.setObjectName(u'%sToolBar' % title)
        # toolbar.setOrientation(Qt.Vertical)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if actions:
            addActions(toolbar, actions)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        return toolbar

class customlog(QWidget):
    def __init__(self):
        super().__init__()

        btn = QPushButton("按鈕",self)
        btn.clicked.connect(self.btnClicked)

    def btnClicked(self):
       msg = QMessageBox(self)
       msg.setWindowTitle("對話框")   #設定文字
       msg.setText("我是訊息")        #設定顯示訊息
       msg.setIcon(QMessageBox.Warning)
       msg.setStandardButtons(QMessageBox.Ok|QMessageBox.No)
       msg.exec()    


# PyQt5: TypeError: unhashable type: 'QListWidgetItem'
class HashableQListWidgetItem(QListWidgetItem):

    def __init__(self, *args):
        super(HashableQListWidgetItem, self).__init__(*args)

    def __hash__(self):
        return hash(id(self))


class MainWindow(QMainWindow, WindowMixin):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = list(range(3))

    def __init__(self, defaultFilename=None, defaultPrefdefClassFile=None):
        super(MainWindow, self).__init__()
        self.setWindowTitle(__appname__)
        # Save as Pascal voc xml
        self.defaultSaveDir = None
        self.usingPascalVocFormat = True
        # For loading all image under a directory
        self.mImgList = []
        self.dirname = None
        self.labelHist = []
        self.lastOpenDir = None
        

        # Whether we need to save or not.
        self.dirty = False

        self.isEnableCreate = True
        self.isEnableCreateRo = True

        # Enble auto saving if pressing next
        self.autoSaving = True
        self._noSelectionSlot = False
        self._beginner = True
        self.screencastViewer = "firefox"
        self.screencast = "https://youtu.be/7D5lvol_QRA"
        # For a demo of original labelImg, please see "https://youtu.be/p0nR2YsCY_U"

        # Main widgets and related state.
        self.labelDialog = LabelDialog(parent=self, listItem=self.labelHist)
        
        self.itemsToShapes = {}
        self.shapesToItems = {}
        self.prevLabelText = ''

        listLayout = QVBoxLayout()
        listLayout.setContentsMargins(0, 0, 0, 0)

        # Create a widget for using default label
        self.useDefautLabelCheckbox = QCheckBox(u'使用預設標籤')
        self.useDefautLabelCheckbox.setChecked(False)
        self.defaultLabelTextLine = QLineEdit()
        useDefautLabelQHBoxLayout = QHBoxLayout()       
        useDefautLabelQHBoxLayout.addWidget(self.useDefautLabelCheckbox)
        useDefautLabelQHBoxLayout.addWidget(self.defaultLabelTextLine)
        useDefautLabelContainer = QWidget()
        useDefautLabelContainer.setLayout(useDefautLabelQHBoxLayout)

        # Create a widget for edit and diffc button
        self.diffcButton = QCheckBox(u'難度標籤')
        self.diffcButton.setChecked(False)
        self.diffcButton.stateChanged.connect(self.btnstate)
        self.editButton = QToolButton()
        self.editButton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # Add some of widgets to listLayout 
        listLayout.addWidget(self.editButton)
        listLayout.addWidget(self.diffcButton)
        listLayout.addWidget(useDefautLabelContainer)

        # Create and add a widget for showing current label items
        self.labelList = QListWidget()
        labelListContainer = QWidget()
        labelListContainer.setLayout(listLayout)
        self.labelList.itemActivated.connect(self.labelSelectionChanged)
        self.labelList.itemSelectionChanged.connect(self.labelSelectionChanged)
        self.labelList.itemDoubleClicked.connect(self.editLabel)
        # Connect to itemChanged to detect checkbox changes.
        self.labelList.itemChanged.connect(self.labelItemChanged)
        listLayout.addWidget(self.labelList)

        self.dock = QDockWidget(u'標註框', self)
        self.dock.setObjectName(u'標註')
        self.dock.setWidget(labelListContainer)
        
        # "testing" label size

        # Tzutalin 20160906 : Add file list and dock to move faster
        self.fileListWidget = QListWidget()
        self.fileListWidget.itemDoubleClicked.connect(self.fileitemDoubleClicked)
        filelistLayout = QVBoxLayout()
        filelistLayout.setContentsMargins(0, 0, 0, 0)
        filelistLayout.addWidget(self.fileListWidget)
        fileListContainer = QWidget()
        fileListContainer.setLayout(filelistLayout)
        self.filedock = QDockWidget(u'檔案清單', self)
        self.filedock.setObjectName(u'檔案')
        self.filedock.setWidget(fileListContainer)

        self.zoomWidget = ZoomWidget()
        # self.colorDialog = ColorDialog(parent=self)

        self.canvas = Canvas()
        self.canvas.zoomRequest.connect(self.zoomRequest)

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(True)
        self.scrollBars = {
            Qt.Vertical: scroll.verticalScrollBar(),
            Qt.Horizontal: scroll.horizontalScrollBar()
        }
        self.canvas.scrollRequest.connect(self.scrollRequest)

        self.canvas.newShape.connect(self.newShape)
        self.canvas.shapeMoved.connect(self.setDirty)
        self.canvas.selectionChanged.connect(self.shapeSelectionChanged)
        self.canvas.drawingPolygon.connect(self.toggleDrawingSensitive)
        self.canvas.status.connect(self.status)

        self.canvas.hideNRect.connect(self.enableCreate)
        self.canvas.hideRRect.connect(self.enableCreateRo)

        self.setCentralWidget(scroll)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        # Tzutalin 20160906 : Add file list and dock to move faster
        self.addDockWidget(Qt.RightDockWidgetArea, self.filedock)
        self.dockFeatures = QDockWidget.DockWidgetClosable\
            | QDockWidget.DockWidgetFloatable
        self.dock.setFeatures(self.dock.features() ^ self.dockFeatures)
        self.filedock.setFeatures(self.filedock.features() ^ self.dockFeatures)

        self.make_xml_file = Make_xml

        # Actions
        action = partial(newAction, self)
        quit = action('&退出', self.close,
                      'Ctrl+Q', 'quit', u'退出應用程式')

        open = action('&開啟', self.openFile,
                      'Ctrl+O', 'open', u'打開圖像或標籤文件')

        opendir = action('&打開目錄', self.openDir,
                         'Ctrl+u', 'open', u'打開目錄')

        changeSavedir = action('&更改預設儲存的標註目錄', self.changeSavedir,
                               'Ctrl+r', 'open', u'更改預設儲存的標註目錄')

        openAnnotation = action('&打開標註', self.openAnnotation,
                                'Ctrl+Shift+O', 'openAnnotation', u'打開標註')

        openNextImg = action('&下一張圖片', self.openNextImg,
                             'd', 'next', u'打開下一個')
        
        label = action('&標註這張', self.labelthis,
                       '', 'labelthis', u'標註現在這張')
        label.setIcon(QIcon(r"icons\auto.png"))
    
        heartinfo = action('&心臟診斷', self.showheartinfo,
                            '', 'showheartinfo', u'使用語言模型來幫你分析病情吧')
        heartinfo.setIcon(QIcon(r"icons\ollama.png"))

        test = action('', self.testfuntion,
                            '', 'test', u'測試')

        NextAndLabel = action('&標註並下一張', self.NextAndLabel,
                              '', 'nextlabel', u'標註然後下一張')
        NextAndLabel.setIcon(QIcon(r"icons\nextlabel.png"))

        openPrevImg = action('&上一張圖片', self.openPrevImg,
                             'a', 'prev', u'打開上一個')

        verify = action('&驗證圖片', self.verifyImg,
                        'space', 'verify', u'驗證圖片')
        verify.setIcon(QIcon("icons\done.png"))

        AutoLabel = action('&自動標註', self.AutoLabel,
                           'Ctrl+y', 'auto', u'自動標註你的檔案')
        AutoLabel.setIcon(QIcon(r"icons\auto.png"))

        save = action('&保存', self.saveFile,
                      'Ctrl+S', 'save', u'將標註保存到文件', enabled=False)
        saveAs = action('&另存為', self.saveFileAs,
                        'Ctrl+Shift+S', 'save-as', u'將標註保存到不同的文件',
                        enabled=False)
        close = action('&關閉', self.closeFile,
                       'Ctrl+W', 'close', u'關閉當前文件')
        color1 = action('Box &框線顏色', self.chooseColor1,
                        'Ctrl+L', 'color_line', u'選擇框線顏色')
        color2 = action('Box &填充顏色', self.chooseColor2,
                        'Ctrl+Shift+L', 'color', u'選擇框的填充顏色')

        createMode = action('創建矩形框', self.setCreateMode,
                            'Ctrl+N', 'new', u'開始繪製框框', enabled=False)
        editMode = action('&編輯矩形框', self.setEditMode,
                          'Ctrl+J', 'edit', u'移動和編輯框框', enabled=False)

        create = action('創建矩形框', self.createShape,
                        'w', 'new', u'繪製一個新框框', enabled=False)

        createRo = action('創建旋轉矩形框', self.createRoShape,
                        'e', 'newRo', u'繪製一個新的旋轉矩形框', enabled=False)

        delete = action('刪除矩形框', self.deleteSelectedShape,
                        'Delete', 'delete', u'刪除', enabled=False)
        copy = action('&複製矩形框', self.copySelectedShape,
                      'Ctrl+D', 'copy', u'創建選定框的複製品',
                      enabled=False)

        advancedMode = action('&進階模式', self.toggleAdvancedMode,
                              'Ctrl+Shift+A', 'expert', u'切換到進階模式',
                              checkable=True)

        hideAll = action('&隱藏矩形框', partial(self.togglePolygons, False),
                         'Ctrl+H', 'hide', u'隱藏所有框框',
                         enabled=False)
        showAll = action('&顯示矩形框', partial(self.togglePolygons, True),
                         'Ctrl+A', 'hide', u'顯示所有框框',
                         enabled=False)

        help = action('&教程', self.tutorial, 'Ctrl+T', 'help',
                      u'顯示示範')

        zoom = QWidgetAction(self)
        zoom.setDefaultWidget(self.zoomWidget)
        self.zoomWidget.setWhatsThis(
            u"放大或縮小圖片. 也可以透過"
            "畫布上 %s 和 %s ." % (fmtShortcut("Ctrl+[-+]"),
                                             fmtShortcut("Ctrl+Wheel")))
        self.zoomWidget.setEnabled(False)

        zoomIn = action('&放大', partial(self.addZoom, 10),
                        'Ctrl++', 'zoom-in', u'增加縮放級別', enabled=False)
        zoomOut = action('&縮小', partial(self.addZoom, -10),
                         'Ctrl+-', 'zoom-out', u'降低縮放級別', enabled=False)
        zoomOrg = action('&原始大小', partial(self.setZoom, 100),
                         'Ctrl+=', 'zoom', u'縮放至原始大小', enabled=False)
        fitWindow = action('&適應窗口', self.setFitWindow,
                           'Ctrl+F', 'fit-window', u'縮放跟隨窗口大小',
                           checkable=True, enabled=False)
        fitWidth = action('&適應寬度', self.setFitWidth,
                          'Ctrl+Shift+F', 'fit-width', u'縮放跟隨窗口寬度',
                          checkable=True, enabled=False)
        # Group zoom controls into a list for easier toggling.
        zoomActions = (self.zoomWidget, zoomIn, zoomOut,
                       zoomOrg, fitWindow, fitWidth)
        self.zoomMode = self.MANUAL_ZOOM
        self.scalers = {
            self.FIT_WINDOW: self.scaleFitWindow,
            self.FIT_WIDTH: self.scaleFitWidth,
            # Set to one to scale to 100% when loading files.
            self.MANUAL_ZOOM: lambda: 1,
        }

        edit = action('&編輯標註', self.editLabel,
                      'Ctrl+E', 'edit', u'修改選定框的標註',
                      enabled=False)
        self.editButton.setDefaultAction(edit)

        shapeLineColor = action('&形狀與線條顏色', self.chshapeLineColor,
                                icon='color_line', tip=u'更改此特定形狀的線條顏色',
                                enabled=False)
        shapeFillColor = action('&形狀與填充顏色', self.chshapeFillColor,
                                icon='color', tip=u'更改此特定形狀的填充顏色',
                                enabled=False)

        labels = self.dock.toggleViewAction()
        labels.setText('顯示/隱藏標註面板')
        #labels.setShortcut('Ctrl+Shift+L')

        # Lavel list context menu.
        labelMenu = QMenu()
        addActions(labelMenu, (edit, delete))
        self.labelList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.labelList.customContextMenuRequested.connect(
            self.popLabelListMenu)

        # Store actions for further handling.
        self.actions = struct(save=save, saveAs=saveAs, open=open, close=close,
                              lineColor=color1, fillColor=color2,
                              create=create, createRo=createRo, delete=delete, edit=edit, copy=copy,
                              createMode=createMode, editMode=editMode, advancedMode=advancedMode,
                              shapeLineColor=shapeLineColor, shapeFillColor=shapeFillColor,
                              zoom=zoom, zoomIn=zoomIn, zoomOut=zoomOut, zoomOrg=zoomOrg,
                              fitWindow=fitWindow, fitWidth=fitWidth,
                              zoomActions=zoomActions,
                              fileMenuActions=(
                                  open, opendir, save, saveAs, close, quit),
                              beginner=(), advanced=(),
                              editMenu=(edit, copy, delete,
                                        None, color1, color2),
                              beginnerContext=(create, edit, copy, delete),
                              advancedContext=(createMode, editMode, edit, copy,
                                               delete, shapeLineColor, shapeFillColor),
                              onLoadActive=(
                                  close, create, createMode, editMode),
                              onShapesPresent=(saveAs, hideAll, showAll))

        self.menus = struct(
            file=self.menu('&文件'),
            edit=self.menu('&編輯'),
            view=self.menu('&查看'),
            help=self.menu('&幫助'),
            recentFiles=QMenu('&打開最近的文件'),
            labelList=labelMenu)

        addActions(self.menus.file,
                   (open, opendir, changeSavedir, openAnnotation, self.menus.recentFiles, save, saveAs, close, None, quit))
        addActions(self.menus.help, (help,))
        addActions(self.menus.view, (
            labels, advancedMode, None,
            hideAll, showAll, None,
            zoomIn, zoomOut, zoomOrg, None,
            fitWindow, fitWidth))

        self.menus.file.aboutToShow.connect(self.updateFileMenu)

        # Custom context menu for the canvas widget:
        addActions(self.canvas.menus[0], self.actions.beginnerContext)
        addActions(self.canvas.menus[1], (
            action('&複製到這裡', self.copyShape),
            action('&移動到這裡', self.moveShape)))

        self.tools = self.toolbar('Tools')
        self.actions.beginner = (
            opendir, openPrevImg, openNextImg, None, label, AutoLabel, heartinfo, test, verify, save, None, create, createRo, copy, delete, None,
            zoomIn, zoom, zoomOut, fitWindow, fitWidth)

        self.actions.advanced = (
            open, save, None,
            createMode, editMode, None,
            hideAll, showAll)

        self.statusBar().showMessage('%s 啟動' % __appname__)
        self.statusBar().show()

        # Application state.
        self.image = QImage()
        self.filePath = ustr(defaultFilename)
        self.recentFiles = []
        self.maxRecent = 7
        self.lineColor = None
        self.fillColor = None
        self.zoom_level = 100
        self.fit_window = False
        # Add Chris
        self.difficult = False

        # Load predefined classes to the list
        self.loadPredefinedClasses(defaultPrefdefClassFile)
        # XXX: Could be completely declarative.
        # Restore application settings.
        if have_qstring():
            types = {
                'filename': QString,
                'recentFiles': QStringList,
                'window/size': QSize,
                'window/position': QPoint,
                'window/geometry': QByteArray,
                'line/color': QColor,
                'fill/color': QColor,
                'advanced': bool,
                # Docks and toolbars:
                'window/state': QByteArray,
                'savedir': QString,
                'lastOpenDir': QString,
            }
        else:
            types = {
                'filename': str,
                'recentFiles': list,
                'window/size': QSize,
                'window/position': QPoint,
                'window/geometry': QByteArray,
                'line/color': QColor,
                'fill/color': QColor,
                'advanced': bool,
                # Docks and toolbars:
                'window/state': QByteArray,
                'savedir': str,
                'lastOpenDir': str,
            }

        self.settings = settings = Settings(types)
        self.recentFiles = list(settings.get('recentFiles', []))
        size = settings.get('window/size', QSize(600, 500))
        position = settings.get('window/position', QPoint(0, 0))
        self.resize(size)
        self.move(position)
        saveDir = ustr(settings.get('savedir', None))
        self.lastOpenDir = ustr(settings.get('lastOpenDir', None))
        if saveDir is not None and os.path.exists(saveDir):
            self.defaultSaveDir = saveDir
            self.statusBar().showMessage('%s 開始. 標註將會被儲存到 %s' %
                                         (__appname__, self.defaultSaveDir))
            self.statusBar().show()

        # or simply:
        # self.restoreGeometry(settings['window/geometry']
        self.restoreState(settings.get('window/state', QByteArray()))
        self.lineColor = QColor(settings.get('line/color', Shape.line_color))
        self.fillColor = QColor(settings.get('fill/color', Shape.fill_color))
        Shape.line_color = self.lineColor
        Shape.fill_color = self.fillColor
        # Add chris
        Shape.difficult = self.difficult

        def xbool(x):
            if isinstance(x, QVariant):
                return x.toBool()
            return bool(x)

        if xbool(settings.get('advanced', False)):
            self.actions.advancedMode.setChecked(True)
            self.toggleAdvancedMode()

        # Populate the File menu dynamically.
        self.updateFileMenu()
        # Since loading the file may take some time, make sure it runs in the
        # background.
        self.queueEvent(partial(self.loadFile, self.filePath or ""))

        # Callbacks:
        self.zoomWidget.valueChanged.connect(self.paintCanvas)

        self.populateModeActions()

    ## Support Functions ##

    def noShapes(self):
        return not self.itemsToShapes

    def toggleAdvancedMode(self, value=True):
        self._beginner = not value
        self.canvas.setEditing(True)
        self.populateModeActions()
        self.editButton.setVisible(not value)
        if value:
            self.actions.createMode.setEnabled(True)
            self.actions.editMode.setEnabled(False)
            # self.dock.setFeatures(self.dock.features() | self.dockFeatures)
        else:
            pass
            # self.dock.setFeatures(self.dock.features() ^ self.dockFeatures)

    def populateModeActions(self):
        if self.beginner():
            tool, menu = self.actions.beginner, self.actions.beginnerContext
        else:
            tool, menu = self.actions.advanced, self.actions.advancedContext
        self.tools.clear()
        addActions(self.tools, tool)
        self.canvas.menus[0].clear()
        addActions(self.canvas.menus[0], menu)
        self.menus.edit.clear()
        actions = (self.actions.create,) if self.beginner()\
            else (self.actions.createMode, self.actions.editMode)
        addActions(self.menus.edit, actions + self.actions.editMenu)

    def setBeginner(self):
        self.tools.clear()
        addActions(self.tools, self.actions.beginner)

    def setAdvanced(self):
        self.tools.clear()
        addActions(self.tools, self.actions.advanced)

    def setDirty(self):
        self.dirty = True
        self.canvas.verified = False
        self.actions.save.setEnabled(True)

    def setClean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.create.setEnabled(True)
        self.actions.createRo.setEnabled(True)

    def enableCreate(self,b):
        self.isEnableCreate = not b
        self.actions.create.setEnabled(self.isEnableCreate)

    def enableCreateRo(self,b):
        self.isEnableCreateRo = not b
        self.actions.createRo.setEnabled(self.isEnableCreateRo)

    def toggleActions(self, value=True):
        """Enable/Disable widgets which depend on an opened image."""
        for z in self.actions.zoomActions:
            z.setEnabled(value)
        for action in self.actions.onLoadActive:
            action.setEnabled(value)

    def queueEvent(self, function):
        QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        # print(message)
        self.statusBar().showMessage(message, delay)
        self.statusBar().show()

    def resetState(self):
        self.itemsToShapes.clear()
        self.shapesToItems.clear()
        self.labelList.clear()
        self.filePath = None
        self.imageData = None
        self.labelFile = None
        self.canvas.resetState()

    def currentItem(self):
        items = self.labelList.selectedItems()
        if items:
            return items[0]
        return None

    def addRecentFile(self, filePath):
        if filePath in self.recentFiles:
            self.recentFiles.remove(filePath)
        elif len(self.recentFiles) >= self.maxRecent:
            self.recentFiles.pop()
        self.recentFiles.insert(0, filePath)

    def beginner(self):
        return self._beginner

    def advanced(self):
        return not self.beginner()

    ## Callbacks ##
    def tutorial(self):
        subprocess.Popen([self.screencastViewer, self.screencast])

    # create Normal Rect
    def createShape(self):
        assert self.beginner()
        self.canvas.setEditing(False)
        self.canvas.canDrawRotatedRect = False
        self.actions.create.setEnabled(False)
        self.actions.createRo.setEnabled(False)

    # create Rotated Rect
    def createRoShape(self):
        assert self.beginner()
        self.canvas.setEditing(False)
        self.canvas.canDrawRotatedRect = True
        self.actions.create.setEnabled(False)
        self.actions.createRo.setEnabled(False)

    def toggleDrawingSensitive(self, drawing=True):
        """In the middle of drawing, toggling between modes should be disabled."""
        self.actions.editMode.setEnabled(not drawing)
        if not drawing and self.beginner():
            # Cancel creation.
            print('Cancel creation.')
            self.canvas.setEditing(True)
            self.canvas.restoreCursor()
            self.actions.create.setEnabled(True)
            self.actions.createRo.setEnabled(True)
            

    def toggleDrawMode(self, edit=True):
        self.canvas.setEditing(edit)
        self.actions.createMode.setEnabled(edit)
        self.actions.editMode.setEnabled(not edit)

    def setCreateMode(self):
        print('setCreateMode')
        assert self.advanced()
        self.toggleDrawMode(False)

    def setEditMode(self):
        assert self.advanced()
        self.toggleDrawMode(True)

    def updateFileMenu(self):
        currFilePath = self.filePath

        def exists(filename):
            return os.path.exists(filename)
        menu = self.menus.recentFiles
        menu.clear()
        files = [f for f in self.recentFiles if f !=
                 currFilePath and exists(f)]
        for i, f in enumerate(files):
            icon = newIcon('labels')
            action = QAction(
                icon, '&%d %s' % (i + 1, QFileInfo(f).fileName()), self)
            action.triggered.connect(partial(self.loadRecent, f))
            menu.addAction(action)

    def popLabelListMenu(self, point):
        self.menus.labelList.exec_(self.labelList.mapToGlobal(point))

    def editLabel(self, item=None):
        if not self.canvas.editing():
            return
        item = item if item else self.currentItem()
        text = self.labelDialog.popUp(item.text())
        if text is not None:
            item.setText(text)
            self.setDirty()

    # Tzutalin 20160906 : Add file list and dock to move faster
    def fileitemDoubleClicked(self, item=None):
        currIndex = self.mImgList.index(ustr(item.text()))
        if currIndex < len(self.mImgList):
            filename = self.mImgList[currIndex]
            if filename:
                self.loadFile(filename)

    # Add chris
    def btnstate(self, item= None):
        """ Function to handle difficult examples
         date on each object """
        if not self.canvas.editing():
            return

        item = self.currentItem()
        if not item: # If not selected Item, take the first one
            item = self.labelList.item(self.labelList.count()-1)

        difficult = self.diffcButton.isChecked()

        try:
            shape = self.itemsToShapes[item]
        except:
            pass
        # Checked and Update
        try:
            if difficult != shape.difficult:
                shape.difficult = difficult
                self.setDirty()
            else:  # User probably changed item visibility
                self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    # React to canvas signals.
    def shapeSelectionChanged(self, selected=False):
        if self._noSelectionSlot:
            self._noSelectionSlot = False
        else:
            shape = self.canvas.selectedShape
            if shape:
                self.shapesToItems[shape].setSelected(True)
            else:
                self.labelList.clearSelection()
        self.actions.delete.setEnabled(selected)
        self.actions.copy.setEnabled(selected)
        self.actions.edit.setEnabled(selected)
        self.actions.shapeLineColor.setEnabled(selected)
        self.actions.shapeFillColor.setEnabled(selected)

    def addLabel(self, shape):
        item = HashableQListWidgetItem(shape.label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self.itemsToShapes[item] = shape
        self.shapesToItems[shape] = item
        self.labelList.addItem(item)
        for action in self.actions.onShapesPresent:
            action.setEnabled(True)

    def remLabel(self, shape):
        if shape is None:
            # print('rm empty label')
            return
        item = self.shapesToItems[shape]
        self.labelList.takeItem(self.labelList.row(item))
        del self.shapesToItems[shape]
        del self.itemsToShapes[item]

    def loadLabels(self, shapes):
        s = []
        for label, points, direction, isRotated, line_color, fill_color, difficult in shapes:
            shape = Shape(label=label)
            for x, y in points:
                shape.addPoint(QPointF(x, y))
            shape.difficult = difficult
            shape.direction = direction
            shape.isRotated = isRotated
            shape.close()
            s.append(shape)
            self.addLabel(shape)

            if line_color:
                shape.line_color = QColor(*line_color)
            if fill_color:
                shape.fill_color = QColor(*fill_color)

        self.canvas.loadShapes(s)

    def saveLabels(self, annotationFilePath):
        annotationFilePath = ustr(annotationFilePath)
        if self.labelFile is None:
            self.labelFile = LabelFile()
            self.labelFile.verified = self.canvas.verified

        def format_shape(s):
            return dict(label=s.label,
                        line_color=s.line_color.getRgb()
                        if s.line_color != self.lineColor else None,
                        fill_color=s.fill_color.getRgb()
                        if s.fill_color != self.fillColor else None,
                        points=[(p.x(), p.y()) for p in s.points],
                       # add chris
                        difficult = s.difficult,
                        # You Hao 2017/06/21
                        # add for rotated bounding box
                        direction = s.direction,
                        center = s.center,
                        isRotated = s.isRotated)

        shapes = [format_shape(shape) for shape in self.canvas.shapes]
        # Can add differrent annotation formats here
        try:
            if self.usingPascalVocFormat is True:
                print ('Img: ' + self.filePath + ' -> Its xml: ' + annotationFilePath)
                self.labelFile.savePascalVocFormat(annotationFilePath, shapes, self.filePath, self.imageData,
                                                   self.lineColor.getRgb(), self.fillColor.getRgb())
            else:
                self.labelFile.save(annotationFilePath, shapes, self.filePath, self.imageData,
                                    self.lineColor.getRgb(), self.fillColor.getRgb())
            return True
        except LabelFileError as e:
            self.errorMessage(u'Error saving label data',
                              u'<b>%s</b>' % e)
            return False

    def copySelectedShape(self):
        self.addLabel(self.canvas.copySelectedShape())
        # fix copy and delete
        self.shapeSelectionChanged(True)

    def labelSelectionChanged(self):
        item = self.currentItem()
        if item and self.canvas.editing():
            self._noSelectionSlot = True
            self.canvas.selectShape(self.itemsToShapes[item])
            shape = self.itemsToShapes[item]
            # Add Chris
            self.diffcButton.setChecked(shape.difficult)

    def labelItemChanged(self, item):
        shape = self.itemsToShapes[item]
        label = item.text()
        if label != shape.label:
            shape.label = item.text()
            self.setDirty()
        else:  # User probably changed item visibility
            self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)

    # Callback functions:
    def newShape(self):
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        if not self.useDefautLabelCheckbox.isChecked() or not self.defaultLabelTextLine.text():
            if len(self.labelHist) > 0:
                self.labelDialog = LabelDialog(
                    parent=self, listItem=self.labelHist)

            text = self.labelDialog.popUp(text=self.prevLabelText)
        else:
            text = self.defaultLabelTextLine.text()

        # Add Chris
        self.diffcButton.setChecked(False)
        if text is not None:
            self.prevLabelText = text
            self.addLabel(self.canvas.setLastLabel(text))
            if self.beginner():  # Switch to edit mode.
                self.canvas.setEditing(True)
                self.actions.create.setEnabled(self.isEnableCreate)
                self.actions.createRo.setEnabled(self.isEnableCreateRo)
            else:
                self.actions.editMode.setEnabled(True)
            self.setDirty()

            if text not in self.labelHist:
                self.labelHist.append(text)
        else:
            # self.canvas.undoLastLine()
            self.canvas.resetAllLines()

    def scrollRequest(self, delta, orientation):
        units = - delta / (8 * 15)
        bar = self.scrollBars[orientation]
        bar.setValue(bar.value() + bar.singleStep() * units)

    def setZoom(self, value):
        self.actions.fitWidth.setChecked(False)
        self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.MANUAL_ZOOM
        self.zoomWidget.setValue(value)

    def addZoom(self, increment=10):
        self.setZoom(self.zoomWidget.value() + increment)

    def zoomRequest(self, delta):
        units = delta / (8 * 15)
        scale = 10
        self.addZoom(scale * units)

    def setFitWindow(self, value=True):
        if value:
            self.actions.fitWidth.setChecked(False)
        self.zoomMode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
        self.adjustScale()

    def setFitWidth(self, value=True):
        if value:
            self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
        self.adjustScale()

    def togglePolygons(self, value):
        for item, shape in self.itemsToShapes.items():
            item.setCheckState(Qt.Checked if value else Qt.Unchecked)

    def loadFile(self, filePath=None):
        """Load the specified file, or the last opened file if None."""
        self.resetState()
        self.canvas.setEnabled(False)
        if filePath is None:
            filePath = self.settings.get('filename')

        unicodeFilePath = ustr(filePath)
        # Tzutalin 20160906 : Add file list and dock to move faster
        # Highlight the file item
        if unicodeFilePath and self.fileListWidget.count() > 0:
            index = self.mImgList.index(unicodeFilePath)
            fileWidgetItem = self.fileListWidget.item(index)
            fileWidgetItem.setSelected(True)

        if unicodeFilePath and os.path.exists(unicodeFilePath):
            if LabelFile.isLabelFile(unicodeFilePath):
                try:
                    self.labelFile = LabelFile(unicodeFilePath)
                except LabelFileError as e:
                    self.errorMessage(u'開啟檔案錯誤',
                                      (u"<p><b>%s</b></p>"
                                       u"<p>請確認 <i>%s</i> 是一個有效的標註檔案.")
                                      % (e, unicodeFilePath))
                    self.status("%s 讀取錯誤" % unicodeFilePath)
                    return False
                self.imageData = self.labelFile.imageData
                self.lineColor = QColor(*self.labelFile.lineColor)
                self.fillColor = QColor(*self.labelFile.fillColor)
            else:
                # Load image:
                # read data first and store for saving into label file.
                self.imageData = read(unicodeFilePath, None)
                self.labelFile = None
            image = QImage.fromData(self.imageData)
            if image.isNull():
                self.errorMessage(u'開啟檔案錯誤',
                                  u"<p>請確認 <i>%s</i> 是一個有效的影像檔案." % unicodeFilePath)
                self.status("%s 讀取錯誤" % unicodeFilePath)
                return False
            self.status("Loaded %s" % os.path.basename(unicodeFilePath))
            self.image = image
            self.filePath = unicodeFilePath
            self.canvas.loadPixmap(QPixmap.fromImage(image))
            if self.labelFile:
                self.loadLabels(self.labelFile.shapes)
            self.setClean()
            self.canvas.setEnabled(True)
            self.adjustScale(initial=True)
            self.paintCanvas()
            self.addRecentFile(self.filePath)
            self.toggleActions(True)

            # Label xml file and show bound box according to its filename
            if self.usingPascalVocFormat is True:
                if self.defaultSaveDir is not None:
                    basename = os.path.basename(
                        os.path.splitext(self.filePath)[0]) + XML_EXT
                    xmlPath = os.path.join(self.defaultSaveDir, basename)
                    self.loadPascalXMLByFilename(xmlPath)
                else:
                    xmlPath = filePath.split(".")[0] + XML_EXT
                    if os.path.isfile(xmlPath):
                        self.loadPascalXMLByFilename(xmlPath)

            self.setWindowTitle(__appname__ + ' ' + filePath)

            # Default : select last item if there is at least one item
            if self.labelList.count():
                self.labelList.setCurrentItem(self.labelList.item(self.labelList.count()-1))
                # self.labelList.setItemSelected(self.labelList.item(self.labelList.count()-1), True)

            self.canvas.setFocus(True)
            return True
        return False

    def resizeEvent(self, event):
        if self.canvas and not self.image.isNull()\
           and self.zoomMode != self.MANUAL_ZOOM:
            self.adjustScale()
        super(MainWindow, self).resizeEvent(event)

    def paintCanvas(self):
        assert not self.image.isNull(), "沒有圖片"
        self.canvas.scale = 0.01 * self.zoomWidget.value()
        self.canvas.adjustSize()
        self.canvas.update()

    def adjustScale(self, initial=False):
        value = self.scalers[self.FIT_WINDOW if initial else self.zoomMode]()
        self.zoomWidget.setValue(int(100 * value))
            
    def scaleFitWindow(self):
        """Figure out the size of the pixmap in order to fit the main widget."""
        e = 2.0  # So that no scrollbars are generated.
        w1 = self.centralWidget().width() - e
        h1 = self.centralWidget().height() - e
        a1 = w1 / h1
        # Calculate a new scale value based on the pixmap's aspect ratio.
        w2 = self.canvas.pixmap.width() - 0.0
        h2 = self.canvas.pixmap.height() - 0.0
        a2 = w2 / h2
        return w1 / w2 if a2 >= a1 else h1 / h2

    def scaleFitWidth(self):
        # The epsilon does not seem to work too well here.
        w = self.centralWidget().width() - 2.0
        return w / self.canvas.pixmap.width()

    def closeEvent(self, event):
        if not self.mayContinue():
            event.ignore()
        s = self.settings
        # If it loads images from dir, don't load it at the begining
        if self.dirname is None:
            s['filename'] = self.filePath if self.filePath else ''
        else:
            s['filename'] = ''

        s['window/size'] = self.size()
        s['window/position'] = self.pos()
        s['window/state'] = self.saveState()
        s['line/color'] = self.lineColor
        s['fill/color'] = self.fillColor
        s['recentFiles'] = self.recentFiles
        s['advanced'] = not self._beginner
        if self.defaultSaveDir is not None and len(self.defaultSaveDir) > 1:
            s['savedir'] = ustr(self.defaultSaveDir)
        else:
            s['savedir'] = ""

        if self.lastOpenDir is not None and len(self.lastOpenDir) > 1:
            s['lastOpenDir'] = self.lastOpenDir
        else:
            s['lastOpenDir'] = ""

    ## User Dialogs ##

    def loadRecent(self, filename):
        if self.mayContinue():
            self.loadFile(filename)

    def scanAllImages(self, folderPath):
        extensions = ['.jpeg', '.jpg', '.png', '.bmp']
        images = []

        for root, dirs, files in os.walk(folderPath):
            for file in files:
                if file.lower().endswith(tuple(extensions)):
                    relatviePath = os.path.join(root, file)
                    path = ustr(os.path.abspath(relatviePath))
                    images.append(path)
        images.sort(key=lambda x: x.lower())
        return images

    def changeSavedir(self, _value=False):
        if self.defaultSaveDir is not None:
            path = ustr(self.defaultSaveDir)
        else:
            path = '.'

        Save_dirpath = ustr(QFileDialog.getExistingDirectory(self,
                                                       '%s - 選擇儲存路徑' % __appname__, path,  QFileDialog.ShowDirsOnly
                                                       | QFileDialog.DontResolveSymlinks))

        if Save_dirpath is not None and len(Save_dirpath) > 1:
            self.defaultSaveDir = Save_dirpath

        self.statusBar().showMessage('%s . 標註檔將會被儲存到 %s' %
                                     ('變更儲存資料夾', self.defaultSaveDir))
        self.statusBar().show()

    def openAnnotation(self, _value=False):
        if self.filePath is None:
            return

        path = os.path.dirname(ustr(self.filePath))\
            if self.filePath else '.'
        if self.usingPascalVocFormat:
            filters = "開啟標註檔案 (%s)" % \
                      ' '.join(['*.xml'])
            filename = QFileDialog.getOpenFileName(self,'%s - 選擇xml檔' % __appname__, path, filters)
            if filename:
                if isinstance(filename, (tuple, list)):
                    filename = filename[0]
            self.loadPascalXMLByFilename(filename)

    def openDir(self, _value=False):
        if not self.mayContinue():
            return

        path = os.path.dirname(self.filePath)\
            if self.filePath else '.'

        if self.lastOpenDir is not None and len(self.lastOpenDir) > 1:
            path = self.lastOpenDir
        global dirpath
        dirpath = ustr(QFileDialog.getExistingDirectory(self,
                                                     '%s - 開啟路徑' % __appname__, path,  QFileDialog.ShowDirsOnly
                                                     | QFileDialog.DontResolveSymlinks))
        
        if dirpath is not None and len(dirpath) > 1:
            self.lastOpenDir = dirpath

        self.dirname = dirpath
        self.filePath = None
        self.fileListWidget.clear()
        self.mImgList = self.scanAllImages(dirpath)
        self.openNextImg()
        for imgPath in self.mImgList:
            item = QListWidgetItem(imgPath)
            self.fileListWidget.addItem(item)

    def verifyImg(self, _value=False):
        # Proceding next image without dialog if having any label
         if self.filePath is not None:
            try:
                self.labelFile.toggleVerify()
            except AttributeError:
                # If the labelling file does not exist yet, create if and
                # re-save it with the verified attribute.
                self.saveFile()
                if self.labelFile is not None:
                    self.labelFile.toggleVerify()
            if self.labelFile is not None:
                self.canvas.verified = True
            self.paintCanvas()
            self.saveFile()

    def openPrevImg(self, _value=False):
        if not self.mayContinue():
            return

        if len(self.mImgList) <= 0:
            return

        if self.filePath is None:
            return

        currIndex = self.mImgList.index(self.filePath)
        if currIndex - 1 >= 0:
            filename = self.mImgList[currIndex - 1]
            if filename:
                self.loadFile(filename)

    def openNextImg(self, _value=False):
        # Proceding next image without dialog if having any label
        if self.autoSaving is True and self.defaultSaveDir is not None:
            if self.dirty is True: 
                self.dirty = False
                self.canvas.verified = True               
                self.saveFile()

        if not self.mayContinue():
            return

        if len(self.mImgList) <= 0:
            return

        filename = None
        if self.filePath is None:
            filename = self.mImgList[0]
        else:
            currIndex = self.mImgList.index(self.filePath)
            if currIndex + 1 < len(self.mImgList):
                filename = self.mImgList[currIndex + 1]

        if filename:
            self.loadFile(filename)

    def NextAndLabel(self, _value=False):
        filename = None
        if self.filePath is None:
            filename = self.mImgList[0]
            self.errorMessage(u'錯誤 沒有偵測到檔案',u'<p>請檢察是否有開啟圖片檔')
        else:
            self.make_xml_file.summon_xml(self.filePath)
            currIndex = self.mImgList.index(self.filePath)
            self.mImgList = self.scanAllImages(dirpath)
            self.fileListWidget.clear()
            for imgPath in self.mImgList:
                item = QListWidgetItem(imgPath)
                self.fileListWidget.addItem(item)
            if currIndex + 1 < len(self.mImgList):
                filename = self.mImgList[currIndex + 1]
        if filename:
            self.loadFile(filename)    

    def labelthis(self, _value=False):
        currIndex = self.mImgList.index(self.filePath)
        self.make_xml_file.summon_xml(self.filePath)
        self.mImgList = self.scanAllImages(dirpath)
        self.fileListWidget.clear()
        for imgPath in self.mImgList:
            item = QListWidgetItem(imgPath)
            self.fileListWidget.addItem(item)
        self.loadFile(self.mImgList[currIndex])
    
    def AutoLabel(self):
        currIndex = self.mImgList.index(self.filePath)
        for imgPath in self.mImgList:
            self.make_xml_file.summon_xml(imgPath)
        self.mImgList = self.scanAllImages(dirpath)
        self.fileListWidget.clear()
        for imgPath in self.mImgList:
            item = QListWidgetItem(imgPath)
            self.fileListWidget.addItem(item)
        self.loadFile(self.mImgList[currIndex])
        print("所有圖片的 XML 文件生成完成！")

    def openFile(self, _value=False):
        if not self.mayContinue():
            return
        path = os.path.dirname(ustr(self.filePath)) if self.filePath else '.'
        formats = ['*.%s' % fmt.data().decode("ascii").lower() for fmt in QImageReader.supportedImageFormats()]
        filters = "圖片及標註檔 (%s)" % ' '.join(formats + ['*%s' % LabelFile.suffix])
        filename = QFileDialog.getOpenFileName(self, '%s - 選擇影像或標註檔' % __appname__, path, filters)
        if filename:
            # self.fileListWidget.clear()
            if isinstance(filename, (tuple, list)):
                filename = filename[0]
            self.loadFile(filename)

    def saveFile(self, _value=False):
        if self.defaultSaveDir is not None and len(ustr(self.defaultSaveDir)):
            if self.filePath:
                imgFileName = os.path.basename(self.filePath)
                savedFileName = os.path.splitext(imgFileName)[0] + XML_EXT
                savedPath = os.path.join(ustr(self.defaultSaveDir), savedFileName)
                self._saveFile(savedPath)
        else:
            imgFileDir = os.path.dirname(self.filePath)
            imgFileName = os.path.basename(self.filePath)
            savedFileName = os.path.splitext(imgFileName)[0] + XML_EXT
            savedPath = os.path.join(imgFileDir, savedFileName)
            self._saveFile(savedPath if self.labelFile
                           else self.saveFileDialog())

    def showheartinfo(self):
        file_path=os.path.splitext(self.filePath)[0] + ".xml"
        print(file_path)
        if os.path.exists(file_path):
            result = self.xml_area(file_path)
            self.heartinfo(*result[:3])
        else:
            print("not found")

    def testfuntion(self):
        print("hello world!!!")
        

    def saveFileAs(self, _value=False):
        assert not self.image.isNull(), "沒有圖片"
        self._saveFile(self.saveFileDialog())

    def saveFileDialog(self):
        caption = '%s - 選擇檔案' % __appname__
        filters = '檔案 (*%s)' % LabelFile.suffix
        openDialogPath = self.currentPath()
        dlg = QFileDialog(self, caption, openDialogPath, filters)
        dlg.setDefaultSuffix(LabelFile.suffix[1:])
        dlg.setAcceptMode(QFileDialog.AcceptSave)
        filenameWithoutExtension = os.path.splitext(self.filePath)[0]
        dlg.selectFile(filenameWithoutExtension)
        dlg.setOption(QFileDialog.DontUseNativeDialog, False)
        if dlg.exec_():
            return dlg.selectedFiles()[0]
        return ''

    def _saveFile(self, annotationFilePath):
        if annotationFilePath and self.saveLabels(annotationFilePath):
            self.setClean()
            self.statusBar().showMessage('儲存到  %s' % annotationFilePath)
            self.statusBar().show()

    def closeFile(self, _value=False):
        if not self.mayContinue():
            return
        self.resetState()
        self.setClean()
        self.toggleActions(False)
        self.canvas.setEnabled(False)
        self.actions.saveAs.setEnabled(False)

    def mayContinue(self):
        return not (self.dirty and not self.discardChangesDialog())

    def discardChangesDialog(self):
        yes, no = QMessageBox.Yes, QMessageBox.No
        msg = u'你有尚未儲存的變更,是否要繼續執行?'
        return yes == QMessageBox.warning(self, u'注意', msg, yes | no)

    def errorMessage(self, title, message):
        return QMessageBox.critical(self, title,
                                    '<p><b>%s</b></p>%s' % (title, message))

    def heartinfo(self, size1, size2, size3):
        dialog = QDialog(self)
        dialog.setWindowTitle('心房心室大小')

        # Set a custom size for the dialog
        dialog.resize(400, 300)

        # Create layout and add widgets
        layout = QVBoxLayout()
        self.errorMessage(u'注意',u'<p>正在思考，按下確認後請勿關閉程式')
        if size1 == 0:
            size1 = u"無"
        else:
            size1=size1*0.00016
        if size2 == 0:
            size2 = u"無"
        else:
            size2=size2*0.00016
        if size3 == 0:
            size3 = u"無"
        else:
            size3=size3*0.00016
        msg = f'右心室 : {size1:.2f} \n右心房 : {size2:.2f} \n左心室 : {size3:.2f}\n'
        response = ollama.chat(
            model = "mistral",
            messages = [{"role":"user","content":f"你現在手裡只有 右心室:{size1}cm,右心房:{size2}cm,左心房:{size3}cm 這些資料來進行分析這個心臟的主人有沒有可能有肺高壓的症狀，病人立即就要一個答案且不接受不確定不明確的答案，請在回應的第一行回應:肺高壓機率: 機率請以百分比回答，換行後大概寫判斷的依據及分析 為了方便閱讀請再回答時每個句號都換行一次"}]
        )
        msg += response['message']['content']
        label = QLabel(msg)
        layout.addWidget(label)
 
        # Add an OK button
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(dialog.accept)
        layout.addWidget(ok_button)
        
        dialog.setLayout(layout)
        dialog.exec()
        

    def currentPath(self):
        return os.path.dirname(self.filePath) if self.filePath else '.'

    def chooseColor1(self):
        color = self.colorDialog.getColor(self.lineColor, u'選擇線條顏色',
                                          default=DEFAULT_LINE_COLOR)
        if color:
            self.lineColor = color
            # Change the color for all shape lines:
            Shape.line_color = self.lineColor
            self.canvas.update()
            self.setDirty()

    def chooseColor2(self):
        color = self.colorDialog.getColor(self.fillColor, u'選擇填充顏色',
                                          default=DEFAULT_FILL_COLOR)
        if color:
            self.fillColor = color
            Shape.fill_color = self.fillColor
            self.canvas.update()
            self.setDirty()

    def deleteSelectedShape(self):
        self.remLabel(self.canvas.deleteSelected())
        self.setDirty()
        if self.noShapes():
            for action in self.actions.onShapesPresent:
                action.setEnabled(False)

    def chshapeLineColor(self):
        color = self.colorDialog.getColor(self.lineColor, u'選擇線條顏色',
                                          default=DEFAULT_LINE_COLOR)
        if color:
            self.canvas.selectedShape.line_color = color
            self.canvas.update()
            self.setDirty()

    def chshapeFillColor(self):
        color = self.colorDialog.getColor(self.fillColor, u'選擇填充顏色',
                                          default=DEFAULT_FILL_COLOR)
        if color:
            self.canvas.selectedShape.fill_color = color
            self.canvas.update()
            self.setDirty()

    def copyShape(self):
        self.canvas.endMove(copy=True)
        self.addLabel(self.canvas.selectedShape)
        self.setDirty()

    def moveShape(self):
        self.canvas.endMove(copy=False)
        self.setDirty()

    def loadPredefinedClasses(self, predefClassesFile):
        if os.path.exists(predefClassesFile) is True:
            with codecs.open(predefClassesFile, 'r', 'utf8') as f:
                for line in f:
                    line = line.strip()
                    if self.labelHist is None:
                        self.lablHist = [line]
                    else:
                        self.labelHist.append(line)

    def loadPascalXMLByFilename(self, xmlPath):
        if self.filePath is None:
            return
        if os.path.isfile(xmlPath) is False:
            return

        tVocParseReader = PascalVocReader(xmlPath)
        shapes = tVocParseReader.getShapes()
        self.loadLabels(shapes)
        self.canvas.verified = tVocParseReader.verified

    def xml_area(self, file_path):
        tree = ET.parse(file_path)
        root = tree.getroot()

        dimensions = [0, 0, 0]

        for obj in root.findall("object"):
            name_element = obj.find("name")
            robndbox = obj.find("robndbox")

            if name_element is not None and robndbox is not None:
                try:
                    name = int(name_element.text)
                    w = float(robndbox.find("w").text)
                    h = float(robndbox.find("h").text)

                    area = w * h
                    if 0 <= name < len(dimensions):
                        dimensions[name] = area
                except (ValueError, IndexError):
                    print(f"Invalid name or dimensions for object: {ET.tostring(obj, encoding='unicode')}")

        return dimensions

class Settings(object):
    """Convenience dict-like wrapper around QSettings."""

    def __init__(self, types=None):
        self.data = QSettings()
        self.types = defaultdict(lambda: QVariant, types if types else {})

    def __setitem__(self, key, value):
        t = self.types[key]
        self.data.setValue(key,
                           t(value) if not isinstance(value, t) else value)

    def __getitem__(self, key):
        return self._cast(key, self.data.value(key))

    def get(self, key, default=None):
        return self._cast(key, self.data.value(key, default))

    def _cast(self, key, value):
        # XXX: Very nasty way of converting types to QVariant methods :P
        t = self.types.get(key)
        if t is not None and t != QVariant:
            if t is str:
                return ustr(value)
            else:
                try:
                    method = getattr(QVariant, re.sub(
                        '^Q', 'to', t.__name__, count=1))
                    return method(value)
                except AttributeError as e:
                    # print(e)
                    return value
        return value


def inverted(color):
    return QColor(*[255 - v for v in color.getRgb()])


def read(filename, default=None):
    try:
        with open(filename, 'rb') as f:
            return f.read()
    except:
        return default


def get_main_app(argv=[]):
    """
    Standard boilerplate Qt application code.
    Do everything but app.exec_() -- so that we can test the application in one thread
    """
    app = QApplication(argv)
    app.setApplicationName(__appname__)
    app.setWindowIcon(newIcon("app"))
    # Tzutalin 201705+: Accept extra agruments to change predefined class file
    # Usage : labelImg.py image predefClassFile
    win = MainWindow(argv[1] if len(argv) >= 2 else None,
                     argv[2] if len(argv) >= 3 else os.path.join('data', 'predefined_classes.txt'))
    win.show()
    return app, win


def main(argv=[]):
    '''construct main app and run it'''
    app, _win = get_main_app(argv)
    return app.exec_()

if __name__ == '__main__':
    sys.exit(main(sys.argv))
