# app.py
from flask import Flask, request, json
import os
import telebot
from telebot import types
from telebot.types import InputMediaPhoto
import vk_api
import re

CALLBACK_KEY = os.getenv('CALLBACK_KEY')
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHANNEL_ID = os.getenv('CHANNEL_ID')
VK_GROUP_ID = os.getenv('VK_GROUP_ID')
ZABOTA_GROUP_ID = os.getenv('ZABOTA_GROUP_ID')
VK_TOKEN = os.getenv('VK_TOKEN')
KEY_WORDS = ['ищем старых хозяев',
             'ищем старых или новых хозяев',
             'Пропал',
             'домашняя',
             'домашний',
             'сбежала',
             'прибилась',
             'потерял',
             'Бегает',
             'хозяин найдись',
             'потерялась',
             'потерялся',
             'ищем',
             'сбежал',
             'появился',
             'найден',
             'в поисках',
             'потеряшка',
             'потеряшки',
             'найти',
             'хозяева отзовитесь',
             'чей',
             'чья',
             'убежал',
             'бегал']

bot = telebot.TeleBot(TG_TOKEN)
bot.remove_webhook()
bot.set_webhook(url='https://bddf-37-145-201-12.ngrok.io/' + TG_TOKEN)
app = Flask(__name__)


def captcha_handler(captcha):
    """ При возникновении капчи вызывается эта функция и ей передается объект
        капчи. Через метод get_url можно получить ссылку на изображение.
        Через метод try_again можно попытаться отправить запрос с кодом капчи
    """

    bot.send_message(TG_CHANNEL_ID, "Enter captcha code {0}: ".format(captcha.get_url()))
    key = None
    # Пробуем снова отправить запрос с капчей
    return captcha.try_again(key)


def get_vk_api():
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    return vk_session.get_api()


def append_username(text, name, user_id):
    return user_link(name, user_id) + "\n" + text


def user_link(name, user_id):
    return "[id" + str(user_id) + '|' + name + ']'


def get_username(vk, user_id):
    user = vk.users.get(user_ids=user_id)
    return user[0]['first_name'] + ' ' + user[0]['last_name']


def post(vk, text, attachment):
    if attachment is None:
        new_post_id = vk.wall.post(owner_id=VK_GROUP_ID, from_group='1', message=text)['post_id']
    else:
        new_post_id = vk.wall.post(owner_id=VK_GROUP_ID, from_group='1', message=text, attachments=attachment)['post_id']
    return new_post_id


def comment(vk, post_id, name, user_id, repost_id):
    text = user_link(name, user_id) + ', сделан репост в ЗОЖ'
    link = '\nhttps://vk.com/wall-' + ZABOTA_GROUP_ID + '_' + str(repost_id)
    text = text + link
    vk.wall.createComment(owner_id=VK_GROUP_ID, post_id=post_id, from_group='84756379', message=text)


def parse_attachment(income_post):
    try:
        attachments = income_post['attachments']
    except KeyError:
        return None
    new_attachments = ''
    for i in attachments:
        media_type = i['type']
        if media_type == 'link':
            new_attachments = new_attachments + i['link']['url'] + ','
        else:
            media_owner = i[media_type]['owner_id']
            media = i[media_type]["id"]
            new_attachments = new_attachments + media_type + str(media_owner) + '_' + str(media) + ','
    new_attachments = new_attachments.rstrip(',')
    if new_attachments == '':
        return None
    else:
        return new_attachments


def phone_exist(text):
    result = re.findall(r"(?:\+7|8|7)?(?: |-)?\(?9\d{2}\)?(?: |-)?\d{3}(?: |-)?\d{2}(?: |-)?\d{2}", text)
    if not result:
        return False
    else:
        return True


def tg_parse_attachment(post_object):
    try:
        attachments = post_object['attachments']
    except KeyError:
        return []
    new_attachments = []
    for i in attachments:
        media_type = i['type']
        if media_type == 'photo':
            url = i['photo']['sizes'][-2]['url']
            new_attachments.append(InputMediaPhoto(url))
    return new_attachments


def repeated(headers):
    try:
        return headers['X-Retry-Counter']
    except KeyError:
        return None


def include_any_key(text):
    text = text.lower()
    res_list = list(map(lambda word: text.find(word), KEY_WORDS))
    flag = False
    for val in res_list:
        if val >= 0:
            flag = True
    return flag


@app.route('/')
def index():
    return "<h1>Animal Care Bot</h1>"


@app.route('/', methods=['POST'])
def processing():
    # Распаковываем json из пришедшего POST-запроса
    data = json.loads(request.data)
    headers = request.headers
    # Вконтакте в своих запросах всегда отправляет поле типа
    if 'type' not in data.keys():
        return 'not vk'
    if repeated(headers):
        print(data['object'])
        print('skipped repeated')
        return 'ok'
    if data['type'] == 'confirmation':
        return CALLBACK_KEY
    elif data['type'] == 'wall_post_new':
        if data['object']['from_id'] != int(VK_GROUP_ID):
            attaches = tg_parse_attachment(data['object'])
            current_post = data['object']
            text = current_post['text']
            old_post_id = current_post['id']
            from_id = current_post['from_id']
            if attaches:
                bot.send_media_group(TG_CHANNEL_ID, attaches)
            bot.send_message(TG_CHANNEL_ID, f'{text}\nPOST_ID: {str(old_post_id)}')
            # vk part
            if include_any_key(text):
                attachment = parse_attachment(current_post)
                vk = get_vk_api()
                name = get_username(vk, from_id)
                text = append_username(text, name, from_id)
                new_post_id = post(vk, text, attachment)
                if phone_exist(text) and attachment is not None:
                    object_id = f'wall{VK_GROUP_ID}_{str(new_post_id)}'
                    repost_id = vk.wall.repost(object=object_id, group_id=ZABOTA_GROUP_ID)['post_id']
                    comment(vk, new_post_id, name, from_id, repost_id)
                vk.wall.delete(owner_id=VK_GROUP_ID, post_id=old_post_id)
            else:
                markup = types.InlineKeyboardMarkup()
                button1 = types.InlineKeyboardButton('Delete', callback_data='Delete')
                button2 = types.InlineKeyboardButton('Repost', callback_data='Repost')
                markup.row(button1, button2)
                bot.send_message(TG_CHANNEL_ID, f'Пост не размещен О_о {str(old_post_id)}', reply_markup=markup)
        return 'ok'


@bot.callback_query_handler(func=lambda call: call.data in ['Delete', 'Repost'])
def test_callback(call):  # <- passes a CallbackQuery type object to your function
    if call.data == 'Delete':
        markup = types.InlineKeyboardMarkup()
        button2 = types.InlineKeyboardButton('Repost', callback_data='Repost')
        markup.row(button2)
        if len(call.message.reply_markup.keyboard[0]) == 1:
            bot.edit_message_reply_markup(message_id=call.message.id, chat_id=call.message.chat.id)
        else:
            bot.edit_message_reply_markup(message_id=call.message.id, chat_id=call.message.chat.id, reply_markup=markup)
    if call.data == 'Repost':
        markup = types.InlineKeyboardMarkup()
        button1 = types.InlineKeyboardButton('Delete', callback_data='Delete')
        markup.row(button1)
        if len(call.message.reply_markup.keyboard[0]) == 1:
            bot.edit_message_reply_markup(message_id=call.message.id, chat_id=call.message.chat.id)
        else:
            bot.edit_message_reply_markup(message_id=call.message.id, chat_id=call.message.chat.id, reply_markup=markup)


# TG COMMANDS
# @bot.message_handler(commands=['start'])
# def start(message):
#     bot.reply_to(message, 'Hello, ' + message.from_user.first_name)


@bot.message_handler(func=lambda message: True, content_types=['text'])
def echo_message(message):
    markup = types.InlineKeyboardMarkup()
    button1 = types.InlineKeyboardButton('Delete', callback_data='Delete')
    button2 = types.InlineKeyboardButton('Repost', callback_data='Repost')
    markup.row(button1, button2)
    bot.send_message(message.chat.id, message.text, reply_markup=markup)


@app.route('/' + TG_TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200


if __name__ == '__main__':
    # Threaded option to enable multiple instances for multiple user access support
    app.run(threaded=True, port=5000)
