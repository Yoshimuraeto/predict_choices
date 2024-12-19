import pysqlite3
import sys

sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")

import streamlit as st
from streamlit_chat import message

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

import datetime
import pytz

from langchain.chat_models import ChatOpenAI
from langchain_openai import OpenAIEmbeddings
from langchain.prompts.chat import (
    ChatPromptTemplate,
    MessagesPlaceholder,
)

from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory

from langchain_chroma import Chroma
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_history_aware_retriever


class MainR:
    def __init__(self):
        self.chat_model = ChatOpenAI(
            openai_api_key=st.secrets["OPENAI_API_KEY"],
            model_name="gpt-3.5-turbo",
            temperature=0.5,
            streaming=True,
            max_tokens=1024,
        )

        self.embed = OpenAIEmbeddings(
            openai_api_key=st.secrets["OPENAI_API_KEY"],
            model="text-embedding-3-large",
        )

        self.CONTEXTUALIZE_Q_SYSTEM_PROMPT = (
            "Given a chat history and the latest user question "
            "which might reference context in the chat history, "
            "formulate a standalone question which can be understood "
            "without the chat history. Do NOT answer the question, "
            "just reformulate it if needed and otherwise return it as is."
        )

        self.CONTEXTUALIZE_Q_PROMPT = ChatPromptTemplate.from_messages(
            [
                ("assistant", self.CONTEXTUALIZE_Q_SYSTEM_PROMPT),
                MessagesPlaceholder("chat_history"),
                ("user", "{input}"),
            ]
        )

        self.SYSTEM_PREFIX = """あなたはAIエージェントです。
        以下のcontextに基づいて質問に回答して下さい。
        
        {context}"""

        self.PROMPT = ChatPromptTemplate.from_messages(
            [
                ("assistant", self.SYSTEM_PREFIX),
                MessagesPlaceholder(variable_name="chat_history"),
                ("user", "{input}"),
            ]
        )

    def get_session_history(self, session_id: str) -> BaseChatMessageHistory:
        # セッションIDごとの会話履歴の取得
        if "store" not in st.session_state:
            st.session_state.store = {}

        if session_id not in st.session_state.store:
            st.session_state.store[session_id] = ChatMessageHistory()

        return st.session_state.store[session_id]

    def get_ids(self):
        query_params = st.query_params
        st.session_state.user_id = query_params.get("user_id", [None])[0]
        st.session_state.theme = query_params.get("talktheme", [None])[0]

    def prepare_firestore(self):
        try:
            if not firebase_admin._apps:
                type = st.secrets["type"]
                project_id = st.secrets["project_id"]
                private_key_id = st.secrets["private_key_id"]
                private_key = st.secrets["private_key"].replace("\\n", "\n")
                client_email = st.secrets["client_email"]
                client_id = st.secrets["client_id"]
                auth_uri = st.secrets["auth_uri"]
                token_uri = st.secrets["token_uri"]
                auth_provider_x509_cert_url = st.secrets["auth_provider_x509_cert_url"]
                client_x509_cert_url = st.secrets["client_x509_cert_url"]
                universe_domain = st.secrets["universe_domain"]

                # Firebase認証情報を設定
                cred = credentials.Certificate(
                    {
                        "type": type,
                        "project_id": project_id,
                        "private_key_id": private_key_id,
                        "private_key": private_key,
                        "client_email": client_email,
                        "client_id": client_id,
                        "auth_uri": auth_uri,
                        "token_uri": token_uri,
                        "auth_provider_x509_cert_url": auth_provider_x509_cert_url,
                        "client_x509_cert_url": client_x509_cert_url,
                        "universe_domain": universe_domain,
                    }
                )
                default_app = firebase_admin.initialize_app(cred)
            db = firestore.client()
            return db

        except:
            self.disable_chat_input()
            st.error("Firebaseの認証に失敗しました")
            return None

    def prepare_model_with_memory(self, theme):

        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        if "vector_db" not in st.session_state:
            chroma_db_path = f"vector_database/{theme}"
            st.session_state.vector_db = Chroma(
                persist_directory=chroma_db_path,
                embedding_function=self.embed,
            )

        if st.session_state.vector_db._collection.count() <= 0:
            self.disable_chat_input()
            st.error("ベクトルデータベースの読み込みに失敗しました")
        else:
            retriever = st.session_state.vector_db.as_retriever()
            st.session_state.history_aware_retriever = create_history_aware_retriever(
                self.chat_model, retriever, self.CONTEXTUALIZE_Q_PROMPT
            )
            qa_chain = create_stuff_documents_chain(self.chat_model, self.PROMPT)
            rag_chain = create_retrieval_chain(
                st.session_state.history_aware_retriever, qa_chain
            )
            st.session_state.conversational_rag_chain = RunnableWithMessageHistory(
                rag_chain,
                self.get_session_history,
                input_messages_key="input",
                history_messages_key="chat_history",
                output_messages_key="answer",
            )

    def display_chat_history(self):
        st.session_state.chat_placeholder = st.empty()
        # チャットのメッセージの履歴作成と表示
        if "message_history" not in st.session_state:
            st.session_state.message_history = []
        with st.session_state.chat_placeholder.container():
            message(
                st.session_state.initge[0],
                key="init_greeting_plus",
                logo="https://raw.githubusercontent.com/Yoshimuraeto/main-c/refs/heads/main/img/AI_picture.png",
            )
            for i in range(len(st.session_state.message_history)):
                message(
                    st.session_state.message_history[i]["user_content"],
                    is_user=True,
                    key=str(i),
                    logo="https://raw.githubusercontent.com/Yoshimuraeto/main-c/refs/heads/main/img/user_picture.png",
                    seed="Nala",
                )
                key_generated = str(i) + "keyg"
                message(
                    st.session_state.message_history[i]["assistant_content"],
                    key=str(key_generated),
                    logo="https://raw.githubusercontent.com/Yoshimuraeto/main-c/refs/heads/main/img/AI_picture.png",
                )

    def generate_and_store_response(self, user_input, db):
        # AIからの応答を取得
        assistant_response = st.session_state.conversational_rag_chain.invoke(
            {"input": user_input},
            config={"configurable": {"session_id": str(st.session_state.user_id)}},
        )
        # データベースに登録
        now = datetime.datetime.now(pytz.timezone("Asia/Tokyo"))
        doc_ref = db.collection(str(st.session_state.user_id)).document(str(now))
        doc_ref.set({"user": user_input, "asistant": assistant_response["answer"]})
        return assistant_response["answer"]

    def disable_chat_input(self):
        st.session_state["chat_input_disabled"] = True

    def enable_chat_input(self):
        st.session_state["chat_input_disabled"] = False

    def forward(self):
        st.title("MainR Day 1")

        if "count" not in st.session_state:
            st.session_state.count = 0

        if "chat_input_disabled" not in st.session_state:
            st.session_state.chat_input_disabled = False
            st.session_state.db = self.prepare_firestore()
            self.get_ids()
            st.session_state.initge = ["今日は何がありましたか？"]

        if st.session_state.db is None:
            st.error("Firebaseの認証に失敗しました")

        self.prepare_model_with_memory(st.session_state.theme)

        self.display_chat_history()

        if st.session_state.count >= 5:
            group_url = (
                "https://qualtricsxmgjnrsqd4j.qualtrics.com/jfe/form/SV_eWJgtPBlKY1vCKy"
            )
            group_url_with_id = f"{group_url}?user_id={st.session_state.user_id}&day=1"
            st.markdown(
                f'これで今回の会話は終了です。こちらをクリックして今日起こったことを回答してください。: <a href="{group_url_with_id}" target="_blank">リンク</a>',
                unsafe_allow_html=True,
            )
            self.disable_chat_input()

        else:
            if user_input := st.chat_input(
                "メッセージを送る",
                disabled=st.session_state.chat_input_disabled,
                on_submit=self.disable_chat_input(),
            ):
                with st.spinner("Wait for it..."):
                    # AIからの応答を取得、データベースに登録
                    assistant_response = self.generate_and_store_response(
                        user_input, st.session_state.db
                    )

                # チャット履歴にメッセージを追加
                st.session_state.message_history.append(
                    {
                        "user_content": user_input,
                        "assistant_content": assistant_response,
                    }
                )

                st.session_state.count += 1

                self.enable_chat_input()
                st.rerun()


if __name__ == "__main__":
    mainr = MainR()
    mainr.forward()
