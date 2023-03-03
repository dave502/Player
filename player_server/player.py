import time

import pygame
from pygame import mixer
from pathlib import Path
from mutagen.mp3 import MP3
import grpc
from concurrent import futures
import player_server.player_pb2_grpc as pb2_grpc
import player_server.player_pb2 as pb2
from typing import Optional
from threading import Thread

class Player(pb2_grpc.PlayerServicer):

    def __init__(self):
        self.playlist:Player.Playlist = self.Playlist()  # двусвязный список объектов SongItem
        self.playing_item: Optional[Player.Playlist.SongItem] = None  # активный объект SongItem
        self.paused:bool = False # на паузе / не на паузе
        self.react_to_next_new_song_event:bool = True # пропустить событие на окончание песни
                                                      # (появляется при нажатии Next)
        self.status:list = [] # список состояний плейера для клиента

        try:
            pygame.init() # модуль для проигрывания файлов
            mixer.music.set_endevent(pb2.NEW_SONG)  # какое событие будет получено при окончании песни
        except Exception as err:
            print(f'Ошибка инициализации музыкального модуля. {err}')
        else:
            try:
                # запуск потока для опроса модуля pygame на событие окончания песни
                Thread(target=self.__end_playing_event, daemon=True).start()
            except Exception as err:
                print(f'Ошибка запуска события. {err}')

    def AddSong(self, request, context) -> pb2.ResponseResult:
        """
        добавляет объекты в двусвязный список
        :param request:
        :param context:
        :return: pb2.ResponseResult
        """
        try:
            self.playlist.append_songs(*request.path)
        except Exception as err:
            return pb2.ResponseResult(error=f'Ошибка добавления файла. {err}')
        else:
            return pb2.ResponseResult()

    def DeleteSong(self, request, context) -> pb2.ResponseResult:
        """
        Удаляет объект из двусвязного списка
        :param request:
        :param context:
        :return: pb2.ResponseResult
        """
        try:
            # удаляется объект только если он не активен в данный момент
            if self.playlist[request.index] is not self.playing_item:
                self.playlist.delete_song(request.index)
        except Exception as err:
            return pb2.ResponseResult(error=f'Ошибка удаления файла. {err}')
        else:
            return pb2.ResponseResult()

    def GetSongIndex(self, request, context) -> pb2.ResponseSongIndex:
        """
        Возвращает порядковый номер активного объекта в двусвязном списке
        :param request:
        :param context:
        :return: ResponseSongIndex
        """
        return pb2.ResponseSongIndex(index=self.__index_playing)

    # этот метод не является эффективным в плане производительности, но
    # он сильно упрощает код синхронизации текущего объекта с клиентом
    @property
    def __index_playing(self) -> int:
        """
        Перебором находится активный объект
        :return: порядковый номер объекта в двусвязном списке
        """
        if self.playing_item:
            for idx, song in enumerate(self.playlist):
                if song is self.playing_item:
                   return idx
        else:
            return -1
        raise LookupError

    def Play(self, request, context) -> pb2.ResponseResult:
        """
        Запучкает проигрывание файла
        :param request:
        :param context:
        :return: ResponseResult
        """
        if request:
            # если запрос на проигрывание получен от пользователя
            # получаем нужный объект по его индексу
            self.playing_item = self.playlist[request.index]
        elif not self.playing_item:
            # если нет активной композиции - проигрывается первая
            self.playing_item = self.playlist.head

        if self.paused:
            # если плеер был на паузе - возобновлем проигрывание
            try:
                mixer.music.unpause()
            except Exception as err:
                return pb2.ResponseResult(error=f'Ошибка возобновления проигрывания. {err}')
            else:
                self.paused = False

        elif self.playing_item:
            # если паузы не было - получем путь к файлу из объекта ItemSong
            path = self.playing_item.song_path
            try:
                # запускаем модуль проигрывания композиции
                mixer.music.load(path)
                mixer.music.play()
            except Exception as err:
                return pb2.ResponseResult(error=f'Ошибка воспроизведения. {err}')

        return pb2.ResponseResult()

    def Pause(self, request, context) -> pb2.ResponseResult:
        """
        Пауза воспроизведения
        :param request:
        :param context:
        :return: ResponseResult
        """
        try:
            mixer.music.pause()
        except Exception as err:
            return pb2.ResponseResult(error=f'Ошибка приостановки воспроизведения. {err}')
        else:
            self.paused = True
        return pb2.ResponseResult()

    def Stop(self, request, contex) -> pb2.ResponseResult:
        """
        Остановка воспроизведения
        :param request:
        :param contex:
        :return: ResponseResult
        """
        # обнуляется переменная активного объекта и останавливается проигрывание
        self.stopped = True
        self.playing_item = None
        self.paused = False
        mixer.music.stop()
        return pb2.ResponseResult()

    def Next(self, request, contex) -> pb2.ResponseResult:
        """
        Запуск воспроизведения следующей композиции
        :param request:
        :param contex:
        :return: ResponseResult
        """
        # установка не реагировать на эту остановку воспроизведения
        self.react_to_next_new_song_event = False
        # получаем следующую композицию из двусвязного списка
        if next_item:= self.playing_item.next_song:
            try:
                # остановка воспроизведения
                self.Stop(None, None)
            except Exception as err:
                return pb2.ResponseResult(error=f'Ошибка остановки воспроизведения Next. {err}')
            else:
                # установка следующей композиции активной
                self.playing_item = next_item
                # запуск воспроизведения
                self.Play(None, None)
        else:
            # если запрос поступил на проигрывание следующей от последней - игнорируем запрос,
            # но на всякий случай проверяем действительно ли это последний объект в двусвязном списке
            if self.playing_item is not self.playlist.tail:
                return pb2.ResponseResult(error=f'Сбой в структуре плейлиста Next. {RuntimeError}')
        return pb2.ResponseResult()

    def Prev(self, request, contex) -> pb2.ResponseResult:
        """
        Запуск воспроизведения предыдущей композиции
        :param request:
        :param contex:
        :return: ResponseResult
        """
        self.react_to_next_new_song_event = False
        if prev_item := self.playing_item.prev_song:
            try:
                self.Stop(None, None)
            except Exception as err:
                return pb2.ResponseResult(error=f'Ошибка остановки воспроизведения Prev. {err}')
            else:
                self.playing_item = prev_item
                self.Play(None, None)
        else:
            if self.playing_item is not self.playlist.head:
                return pb2.ResponseResult(error=f'Сбой в структуре плейлиста Prev. {RuntimeError}')
        return pb2.ResponseResult()

    def PlayingSongInfo(self, request, context) -> pb2.ResponseSongInformation:
        """
        Возвращает имя и длительность композиции
        :param request:
        :param context:
        :return: ResponseSongInformation
        """
        try:
            # получаем информацию из активного объекта
            song_info =  pb2.ResponseSongInformation(
                title = self.playing_item.song_path.stem,
                duration = self.playing_item.duration)
        except Exception as err:
            return pb2.ResponseResult(error=f'Ошибка получения информации о файле. {err}')
        return song_info

    def SetPosition(self, request, context) -> pb2.ResponseResult:
        """
        Установка позиции трека (не работает)
        :param request:
        :param context:
        :return: ResponseResult
        """
        # Не работает как следует функция установки позиции в библиотеке pygame.mixer
        try:
            mixer.music.play(request.position*1000)
        except Exception as err:
            return pb2.ResponseResult(error=f'Ошибка получения информации о файле. {err}')
        return pb2.ResponseResult()

    def IsPaused(self, request, context) -> pb2.ResponsePaused:
        """
        Находится ли проигрывание в состоянии паузы
        :param request:
        :param context:
        :return: ResponsePaused
        """
        paused = -1
        if self.playing_item:
            paused = int(self.paused)
        return pb2.ResponsePaused(result=paused)

    def GetPlayList(self, request, contex) -> pb2.ResponsePlaylist:
        """
        Возвращает список названий композиций и индекс проигрываемой композиции
        :param request:
        :param contex:
        :return: ResponsePlaylist
        """
        try:
            playlist = pb2.ResponsePlaylist(
                song_title=[str(item) for item in self.playlist],
                playing = self.__index_playing)
        except Exception as err:
            return pb2.ResponseResult(error=f'Ошибка получения плейлиста. {err}')
        return playlist

    def GetPlayerStatus(self, request, contex) -> pb2.ResponsePlayerStatus:
        """
        Возвращает состояние плеера - Воспроизведение/Пауза/Было переключение трека на следующий/
                                      Текущее время проигрывания трека
        :param request:
        :param contex:
        :return: ResponsePlayerStatus
        """
        self.status.append(pb2.PLAYING if self.playing_item else pb2.WAITING)
        if self.paused: self.status.append(pb2.PAUSED)
        try:
            song_position = int(mixer.music.get_pos()/1000)
        except Exception as err:
            return pb2.ResponsePlayerStatus(error=f'Ошибка получения текущей позиции. {err}')

        yield pb2.ResponsePlayerStatus(status=self.status, position=song_position)
        self.status.clear()

    def __end_playing_event(self) -> None:
        """
        функция циклично проверяет объект pygame на наличие события завершения трека
        :return:
        """
        try:
            while True:
                for event in pygame.event.get():
                    if self.react_to_next_new_song_event and event.type == pb2.NEW_SONG:
                        self.status.append(pb2.NEW_SONG)
                        self.Next(None, None)
                    self.react_to_next_new_song_event = True
                time.sleep(0.5)
        except Exception as err:
            raise err

    class Playlist:
        """
        класс двусвязного списка
        """
        head = None
        tail = None

        class SongItem:
            """
            класс объектов двусвязного списка
            """
            def __init__(self, song_path, previous_song=None, next_song=None):
                self.song_path = Path(song_path) # путь к треку
                self.duration = MP3(song_path).info.length # длительность трека
                self.prev_song = previous_song # предыдущий объект
                self.next_song = next_song # следующий объект

            def __str__(self):
                # название трека из его пути
                return self.song_path.stem

        def __init__(self):
            pass

        def append_songs(self, *items):
            """
            добавить объекты в конец двусвязного списка
            :param items:
            :return:
            """
            for item in items:
                if not self.tail:
                    # если это первый объект, то он будет и первым и последним
                    song = self.SongItem(item)
                    self.tail = song
                    self.head = song
                else:
                    # если не первый объект
                    song = self.SongItem(item, previous_song=self.tail)
                    self.tail.next_song = song
                    self.tail = song

        def delete_song(self, index:int) -> None:
            """
            удаление объекта по индексу
            :param index:
            :return:
            """
            # находим удаляемый объект
            deleted_item = self[index]
            if not deleted_item.prev_song:
                # если он первый в списке
                deleted_item.next_song.prev_song = None
                self.head = deleted_item.next_song
            elif not deleted_item.next_song:
                # если он последний в списке
                deleted_item.prev_song.next_song = None
                self.tail = deleted_item.prev_song
            else:
                # если между первым и последним - обновляем ссылки соседних объектов
                deleted_item.prev_song.next_song, deleted_item.next_song.prev_song = \
                    deleted_item.next_song, deleted_item.prev_song
            del deleted_item

        def __getitem__(self, index:int) -> SongItem:
            # выдача объекта по индексу
            item = self.head
            for i in range(index):
                item = item.next_song
            return item

        def __iter__(self):
            # итерируемый двусвязниый список
            item = self.head
            while item is not None:
                yield item
                item = item.next_song


def serve():
    """
    запуск сервера
    :return:
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_PlayerServicer_to_server(Player(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()