from sqlalchemy import create_engine, String, Integer, JSON, ForeignKey, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class ImageRow(Base):
    __tablename__ = 'images'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str]
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)


class JobRow(Base):
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    image_id: Mapped[str] = mapped_column(ForeignKey('images.id'))
    created_at: Mapped[str]
    status: Mapped[str]
    confidence: Mapped[float]
    results: Mapped[list] = mapped_column(JSON)


def init_db(path):
    engine = create_engine(f'sqlite:///{path}', connect_args={'check_same_thread': False, 'timeout': 30})
    @event.listens_for(engine, 'connect')
    def configure(connection, _):
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)
