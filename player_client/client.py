import tkinter
from threading import Thread
from tkinter import ttk
from tkinter import filedialog as fd
from tkinter import *
from pathlib import Path
import asyncio
from asyncio import AbstractEventLoop
import grpc
from player_server import player_pb2_grpc as pb2_grpc
from player_server import player_pb2 as pb2
import logging

window = tkinter.Tk()
window.title('Player')
window.geometry('400x500')


class PlayerGUI:
    """
    класс пользовательского интерфейса
    """
    def __init__(self, loop):
        # путь для выбора файлов
        self.__last_path = '/'
        # элементы интерфейса
        self.playlist_widget = None
        self.prev_button = None
        self.play_button = None
        self.next_button = None
        self.info_playing = None
        self.progressbar = None
        self.status_label = None
        # статус объекта
        self.running = False
        # цикл событий asyncio
        self.__async_loop = loop
        # циклическая задача
        self.get_event_task = None
        # данные сервера
        self.host = '127.0.0.1'
        self.server_port = 50051

    def start(self) -> None:
        """
        запуск интерфейса и подключение к серверу
        :return:
        """
        try:
            """
            BUTTONS
            """
            buttons_frame = ttk.Frame(window, padding=10)
            self.play_button = ttk.Button(buttons_frame, text='>', command=self.play_pause)
            self.next_button = ttk.Button(buttons_frame, text='>>', command=self.play_next)
            self.prev_button = ttk.Button(buttons_frame, text='<<', command=self.play_prev)

            """
            SONG INFO
            """
            info_frame = ttk.Frame(window)
            self.info_playing = ttk.Label(info_frame, text='')
            progress_bar_frame = ttk.Frame(info_frame)
            self.playing_time = ttk.Label(progress_bar_frame)
            self.progressbar = ttk.Progressbar(progress_bar_frame, orient='horizontal', mode='determinate', length=330)
            self.duration = ttk.Label(progress_bar_frame, text='')

            """
            PLAYLIST
            """
            playlist_frame = tkinter.Frame(window, relief='flat', border=2)
            self.playlist_widget = tkinter.Listbox(playlist_frame, height=20, width=400, relief='flat')
            playlist_scroll = ttk.Scrollbar(playlist_frame, orient='vertical')
            playlist_scroll.configure(command=self.playlist_widget.yview)
            self.playlist_widget.configure(background="skyblue4", foreground="white", font=('Aerial 13'),\
                                           yscrollcommand=playlist_scroll.set)
            self.playlist_widget.bind('<Double-1>', self.play)
            self.progressbar.bind('<Button-1>', self.set_song_position)
            playlist_buttons_frame = ttk.Frame(playlist_frame, padding=10)
            add_button = ttk.Button(playlist_buttons_frame, text='Add', command=self.add_files_to_playlist, width=5)
            del_button = ttk.Button(playlist_buttons_frame, text='Del', command=self.remove_item, width=5)

            """
            PLAYER STATUS
            """
            status_frame = ttk.Frame(window)
            self.status_label = ttk.Label(status_frame, text='')

            buttons_frame.pack(side='bottom')
            info_frame.pack(side='bottom')
            progress_bar_frame.pack()
            status_frame.pack(side='top')
            playlist_frame.pack(side='top', fill='y')
            playlist_buttons_frame.pack(side='bottom')

            add_button.pack(side='left')
            del_button.pack(side='left')
            self.playlist_widget.pack(side='left', fill='both')
            playlist_scroll.pack(side='left', fill='both')

            self.prev_button.pack(side='left')
            self.play_button.pack(side='left')
            self.next_button.pack(side='left')

            self.info_playing.pack()
            self.playing_time.pack(side='left')
            self.progressbar.pack(side='left')
            self.duration.pack(side='left')

            self.status_label.pack()
        except Exception as err:
            logging.exception(f"Сбой при инициализации интерфейса. {err}")

        if self.__connect_to_server():
            self.__update_playlist_widget()

    def __connect_to_server(self) ->None:
        """
        Подключение к серверу
        :return:
        """
        try:
            self.channel = grpc.insecure_channel(
                '{}:{}'.format(self.host, self.server_port))
            grpc.channel_ready_future(self.channel).result(timeout=1)
            self.stub = pb2_grpc.PlayerStub(self.channel)
        except Exception as rpc_error:
            logging.warning(f"Отсутствует связь с сервером. {rpc_error}")
            self.status_label['text'] = 'Отсутствует связь с сервером'
            return False
        else:
            self.status_label['text'] = 'Онлайн'
            self.running = True
            return True

    def set_song_position(self, event) -> None:
        """
        Установка позиции проигрываемого трека - не работает
        :param event:
        :return:
        """
        self.stub.SetPosition(pb2.RequestSongPosition(position=event.x))

    def add_files_to_playlist(self):
        """
        Добавляет выбранные файлы на сервер (для упрощения принимается,
        что сервер и клиент на одном компютере)
        :return:
        """
        filetypes = (('Music files', '*.mp3'),('All files', '*.*'))

        try:
            # открыть диалог tkinter и получить список путей
            filenames = fd.askopenfilenames(
                title='Add music files',
                initialdir=self.__last_path,
                filetypes=filetypes)

            if len(filenames):
                # если файлы выбраны - добавить их на сервер
                result = self.stub.AddSong(pb2.RequestSongPath(path=filenames))
                if not result.error:
                    self.__update_playlist_widget()
                    self.last_path = Path(filenames[-1]).parent
                else:
                    self.status_label['text'] = 'Ошибка добавления файла'
                    logging.warning(f"Ошибка добавления файла. {result.error}")
        except Exception as err:
            logging.exception(f"Сбой при добавлении файла. {err}")

    def play_pause(self, event=None):
        """
        Поставить на паузу / Снять с паузы
        :param event:
        :return:
        """
        is_paused = self.stub.IsPaused(pb2.Empty()).result
        if is_paused == 0:
            self.pause()
        else:
            self.play()

    def pause(self):
        """
        Приостановка воспроизведения
        :return:
        """
        result = self.stub.Pause(pb2.Empty())
        if not result.error:
            # остановка прогрессбара
            self.progressbar.stop()
            self.play_button.configure(text=('>'))
        else:
            self.status_label['text'] = result.error
            logging.warning(result.error)

    def play(self, event=None):
        """
        запуск воспроизведения
        :param event:
        :return:
        """
        # если в списке выбран трек - играть его
        selected_item = self.playlist_widget.curselection()[0]
        result = self.stub.Play(pb2.RequestSongIndex(index=selected_item))
        if not result.error:
            # обновить информацию о треке
            self.play_button.configure(text=('||'))
            self.__update_song_info()
        else:
            self.status_label['text'] = result.error
            logging.warning(result.error)

    def stop(self):
        """
          оставновка приложения
          :param event:
          :return:
          """
        # остановка воспроизведения на сервере
        pb2.self.stub.Stop(pb2.Empty())
        # оставновка цикличной задачи опроса сервера
        self.get_event_task.cancel()

    def play_next(self, event=None):
        """
        проигрывание следующего трека
        :param event:
        :return:
        """
        result = self.stub.Next(pb2.Empty())
        if not result.error:
            self.__update_song_info()
        else:
            self.status_label['text'] = result.error
            logging.warning(result.error)

    def play_prev(self, event=None):
        """
         проигрывание предыдущего трека
         :param event:
         :return:
         """
        result = self.stub.Prev(pb2.Empty())
        if not result.error:
            self.__update_song_info()
        else:
            self.status_label['text'] = result.error
            logging.warning(result.error)

    def remove_item(self):
        """
        удаление трека
        :return:
        """
        # получение индекса выбранного трека
        current_index = self.playlist_widget.curselection()[0]
        # удаление
        result = self.stub.DeleteSong(pb2.RequestSongIndex(index=current_index))
        if not result.error:
            self.__update_playlist_widget()
        else:
            self.status_label['text'] = result.error
            logging.warning(result.error)

    def __update_song_info(self):
        """
        обновление элементов интерфейса с информацией о текущем треке
        :return:
        """
        # получение информации с сервера
        song_info = self.stub.PlayingSongInfo(pb2.Empty())
        if not song_info.error:
            # обновление нформации на элементах интерфейса
            self.info_playing['text'] = song_info.title

            duration = song_info.duration
            self.duration['text'] = f'{int(duration//60)}:{int(duration%60):02d}'

            self.progressbar['maximum'] = int(duration)

            song_index = self.stub.GetSongIndex(pb2.Empty())
            if not song_index.error and song_index.index >= 0:
                self.__select_item(song_index.index)

                if song_index.index+1 == self.playlist_widget.size():
                    self.next_button["state"] = "disabled"
                elif song_index.index == 0:
                    self.prev_button["state"] = "disabled"
                else:
                    self.next_button["state"] = "enable"
                    self.prev_button["state"] = "enable"
            else:
                self.status_label['text'] = song_info.error
                logging.warning(song_info.error)
        else:
            self.status_label['text'] = song_info.error
            logging.warning(song_info.error)

    def __update_playlist_widget(self):
        """
        обновить информацию в виджете плейлиста
        :return:
        """
        # очитска виджета
        self.playlist_widget.delete(0,END)
        # получение плейлиста с сервера
        songs_list = self.stub.GetPlayList(pb2.Empty())
        if not songs_list.error:
            # добавление треков на виджет и отметка активного трека
            self.playlist_widget.insert('end', *songs_list.song_title)
            if(len(songs_list.song_title) and songs_list.playing >= 0):
                self.__select_item(songs_list.playing)
            else:
                self.playlist_widget.select_set(0)
        else:
            self.status_label['text'] = songs_list.error
            logging.warning(songs_list.error)

    def __select_item(self, index):
        """
        отметка цветом элемента по индексу
        :param index:
        :return:
        """
        for i in range(self.playlist_widget.size()):
            self.playlist_widget.itemconfig(i,
                                        background='',
                                        foreground='',
                                        selectbackground='',
                                        selectforeground='')
        self.playlist_widget.itemconfig(index,
                                        background='yellow',
                                        foreground='black',
                                        selectbackground='red',
                                        selectforeground='white')

    async def __get_event(self):
        """
        цикличный запрос состояния объекта плеера
        :return:
        """
        while not self.running:
            # подключение к серверу
            self.__connect_to_server()

        while self.running:
            # проверка статуса плеера-сервера и обновление элементов интерфейса
            for response in player_gui.stub.GetPlayerStatus(pb2.Empty()):
                if not response.error:
                    if pb2.NEW_SONG in response.status:
                        self.__update_song_info()
                    if pb2.PLAYING in response.status:
                        self.play_button.configure(text=('||', '>')[pb2.PAUSED in response.status])
                    elif pb2.WAITING in response.status:
                        self.playlist_widget.select_set(0)
                    if response.position >= 0:
                        self.progressbar['value'] = response.position
                        self.playing_time['text'] = f'{int(response.position//60)}:{int(response.position%60):02d}'
                else:
                    self.status_label['text'] = response.error
                    logging.warning(response.error)
            # повторять каждые полсекунды
            await asyncio.sleep(0.5)

    def get_player_events(self):
        # запустить задачу в цикле событий asyncio
        self.get_event_task = self.__async_loop.create_task(self.__get_event())
        result = asyncio.gather(self.get_event_task)


class ThreadedEventLoop(Thread):
    """
    класс потока с циклом событий asyncio
    """
    def __init__(self, loop:AbstractEventLoop):
        super().__init__()
        self._loop = loop
        self.daemon = True

    def run(self):
        self._loop.run_forever()

if __name__ == '__main__':
    try:
        # запуск потока с циклом событий asyncio
        loop = asyncio.new_event_loop()
        asyncio_thread = ThreadedEventLoop(loop)
        asyncio_thread.start()

        # инициализация объекта плеера-клиента
        player_gui = PlayerGUI(loop)
        player_gui.get_player_events()
        player_gui.start()

        # запуск цикла событий tkinter
        window.mainloop()

    except KeyboardInterrupt:
        print('Interrupted')
        player_gui.stop()
        window.quit()
        loop.stop()
        loop.close()