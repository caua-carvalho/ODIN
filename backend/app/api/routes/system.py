import time
from fastapi import APIRouter
from pydantic import BaseModel
import psutil

router = APIRouter()

_start_time = time.time()


class SystemInfo(BaseModel):
    cpu_percent: float
    memory_total: int
    memory_used: int
    memory_percent: float
    disk_total: int
    disk_used: int
    disk_percent: float
    uptime_seconds: float
    load_avg: list[float]


@router.get("", response_model=SystemInfo)
async def get_system_info():
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load = list(psutil.getloadavg())

    return SystemInfo(
        cpu_percent=cpu,
        memory_total=mem.total,
        memory_used=mem.used,
        memory_percent=mem.percent,
        disk_total=disk.total,
        disk_used=disk.used,
        disk_percent=disk.percent,
        uptime_seconds=time.time() - _start_time,
        load_avg=load,
    )
