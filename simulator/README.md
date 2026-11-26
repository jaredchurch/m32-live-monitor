# M32 simulator

The simulator is a planned component of this project. Its target is to provide a virtual
M32 state source for dashboard development and, in a later phase, compatibility with
M32-Edit over OSC.

That compatibility is **not implemented yet**. A basic UDP listener or a dashboard mock
must not be described as an M32-Edit-compatible console.

The simulator will be kept separate from the hardware transport so simulator traffic
cannot reach a physical mixing console by accident.
