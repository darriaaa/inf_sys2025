import time
import random
import psycopg2
from psycopg2 import OperationalError
from prometheus_client import start_http_server, Counter

# Prometheus-метрики
DB_OPS = Counter('db_operations_total', 'Number of DB operations', ['type'])


def get_connection():
    """
    Подключение к PostgreSQL внутри docker-compose.
    Делает бесконечные попытки подключения, пока БД не станет доступной.
    """
    while True:
        try:
            print("[db-loader] Trying to connect to db:5432/appdb ...")
            conn = psycopg2.connect(
                host='db',
                dbname='appdb',
                user='appuser',
                password='apppass'
            )
            conn.autocommit = False
            print("[db-loader] Connected to PostgreSQL.")
            return conn
        except OperationalError as e:
            print("[db-loader] DB is not ready yet, retry in 3 seconds...")
            print(e)
            time.sleep(3)


def init_db(conn):
    """
    Создаём тестовую таблицу для записей.
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS test_data (
                id SERIAL PRIMARY KEY,
                value INT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
    conn.commit()
    print("[db-loader] Table test_data is ready.")


def main_loop():
    conn = get_connection()
    init_db(conn)

    print("[db-loader] Main loop started.")
    while True:
        try:
            with conn.cursor() as cur:
                # INSERT
                val = random.randint(1, 1000)
                cur.execute("INSERT INTO test_data (value) VALUES (%s);", (val,))
                DB_OPS.labels(type='insert').inc()

                # SELECT
                cur.execute("SELECT COUNT(*) FROM test_data;")
                _ = cur.fetchone()
                DB_OPS.labels(type='select').inc()

            conn.commit()
            # чуть-чуть логов, чтобы видеть жизнь
            print(f"[db-loader] Inserted value={val}")
        except OperationalError as e:
            print("[db-loader] Lost connection to DB, reconnecting...")
            print(e)
            # откатываем транзакцию на всякий случай
            try:
                conn.rollback()
            except Exception:
                pass
            conn = get_connection()
            init_db(conn)
        except Exception as e:
            print("[db-loader] DB error:", e)
            try:
                conn.rollback()
            except Exception:
                pass

        time.sleep(2)  # невелика пауза між циклами


if __name__ == '__main__':
    # Prometheus буде скрейпити метрики з порту 8000
    start_http_server(8000)
    print("[db-loader] DB loader started, metrics on :8000/metrics")
    main_loop()

