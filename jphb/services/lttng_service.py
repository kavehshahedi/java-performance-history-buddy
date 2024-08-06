import subprocess


class LTTngService:
    """
    A class to manage LTTng tracing. It starts and stops the tracing and saves the traces to a specified output path.

    Attributes:
        - project_name: The name of the project to trace
        - output_path: The path to save the traces to
        - verbose: A flag to enable verbose

    Methods:
        - start: Start the tracing
        - stop: Stop the tracing
    """

    def __init__(self, project_name:str, output_path:str, verbose: bool = False) -> None:
        self.project_name = project_name
        self.output_path = output_path
        self.verbose = verbose

    def start(self) -> None:
        # Destroy the LTTng session if it already exists
        self.__destroy()

        # Create a new LTTng session
        self.__create_session()

        # Enable the channel
        self.__enable_channel()

        # Enable all kernel and syscalls events
        self.__enable_event()

        # Add the context, including TID, PID, and process name
        self.__add_context('tid')
        self.__add_context('pid')
        self.__add_context('procname')

        # Start the tracing
        self.__start()

    def stop(self) -> None:
        # Stop the tracing
        self.__stop()

        # Destroy the LTTng session
        self.__destroy()

    def __create_session(self) -> None:
        subprocess.run(['lttng',
                        'create',
                        self.project_name,
                        '--output',
                        self.output_path],
                        capture_output=not self.verbose)

    def __enable_channel(self) -> None:
        subprocess.run(['lttng',
                        'enable-channel',
                        '--kernel',
                        '--subbuf-size=64M',
                        '--num-subbuf=8',
                        f'{self.project_name}-channel'],
                        capture_output=not self.verbose)
        
    def __enable_event(self) -> None:
        # Enable some kernel events
        subprocess.run(['lttng',
                        'enable-event',
                        '--kernel',
                        'sched_switch,sched_waking,sched_pi_setprio,sched_process_fork,sched_process_exit,sched_process_free,sched_wakeup,irq_softirq_entry,irq_softirq_raise,irq_softirq_exit,irq_handler_entry,irq_handler_exit,lttng_statedump_process_state,lttng_statedump_start,lttng_statedump_end,lttng_statedump_network_interface,lttng_statedump_block_device,block_rq_complete,block_rq_insert,block_rq_issue,block_bio_frontmerge,sched_migrate,sched_migrate_task,power_cpu_frequency,net_dev_queue,netif_receive_skb,net_if_receive_skb,timer_hrtimer_start,timer_hrtimer_cancel,timer_hrtimer_expire_entry,timer_hrtimer_expire_exit',
                        f'--channel={self.project_name}-channel'],
                        capture_output=not self.verbose)
        
        # Enable all syscalls events
        subprocess.run(['lttng',
                        'enable-event',
                        '--kernel',
                        '--syscall',
                        '--all',
                        f'--channel={self.project_name}-channel'],
                        capture_output=not self.verbose)
        
    def __add_context(self, context: str) -> None:
        subprocess.run(['lttng',
                        'add-context',
                        '--kernel',
                        f'--type={context}',
                        f'--channel={self.project_name}-channel'],
                        capture_output=not self.verbose)
        
    def __start(self) -> None:
        subprocess.run(['lttng',
                        'start',
                        f'{self.project_name}'],
                        capture_output=not self.verbose)
        
    def __stop(self) -> None:
        subprocess.run(['lttng',
                        'stop',
                        f'{self.project_name}'],
                        capture_output=not self.verbose)
        
    def __destroy(self) -> None:
        subprocess.run(['lttng',
                        'destroy',
                        f'{self.project_name}'],
                        capture_output=not self.verbose)